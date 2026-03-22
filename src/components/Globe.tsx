import { useRef, useEffect, useState, useMemo, useCallback, useImperativeHandle, forwardRef } from 'react'
import * as THREE from 'three'
import Globe from 'react-globe.gl'
import { fetchTextOrThrow } from '../utils/fetchTextOrThrow'
import type {
    Office, OfficeType,
    GeoIntelligence, LayerName, MapEntity,
    ChainMatrix, RiskConvergence, ChokepointAnalysis
} from '../types'

const OFFICE_TYPE_COLORS: Record<OfficeType, string> = {
    headquarters: '#1a1a1a',      // Ink Black - Dominant
    regional: '#57534e',          // Warm Grey
    engineering: '#57534e',       // Warm Grey
    satellite: '#a8a29e',         // Light Warm Grey
    manufacturing: '#ea580c',     // Industrial Orange - High Visibility
    data_center: '#0891b2',       // Cyan/Blue - Digital/Cool
    sales: '#15803d',             // Green - Commercial
    logistics: '#b91c1c',         // Red - Critical Path
}

const OFFICE_TYPE_SIZES: Record<OfficeType, number> = {
    headquarters: 1.8,            // Larger
    regional: 0.8,
    engineering: 0.7,
    satellite: 0.4,               // Smaller
    manufacturing: 1.2,           // Significant
    data_center: 1.0,
    sales: 0.6,
    logistics: 0.8,
}

const CRITICALITY_COLORS: Record<string, string> = {
    critical: '#b91c1c',          // Deep Red
    important: '#ea580c',         // Orange
    standard: '#57534e',          // Grey
}

// Risk Gradient: Neutral Yellow -> Deep Burgundy
const RISK_COLORS: Record<number, string> = {
    1: '#eab308', // Yellow-500
    2: '#d97706', // Amber-600
    3: '#f97316', // Orange-500
    4: '#ea580c', // Orange-600
    5: '#dc2626', // Red-600
    6: '#b91c1c', // Red-700
    7: '#991b1b', // Red-800
    8: '#7f1d1d', // Red-900
    9: '#450a0a', // Brown/Red
    10: '#450a0a',
}

export interface GlobeViewHandle {
    flyTo: (lat: number, lng: number, altitude?: number) => void
}

interface IntelNodeDatum {
    lat: number
    lng: number
    layerType: 'office' | 'supplyChain' | 'customer' | 'risk' | 'chokepoint' | 'regionalRisk'
    label: string
    sublabel: string
    detail: string
    color: string
    id: string
    entity: MapEntity
}

interface GlobeViewProps {
    viewMode: 'global' | 'company'
    offices: Office[]
    onEntityClick: (entity: MapEntity | null) => void
    selectedEntity: MapEntity | null
    intel: GeoIntelligence | null
    chainMatrix: ChainMatrix | null
    riskConvergence: RiskConvergence | null
    chokepointAnalysis: ChokepointAnalysis | null
    activeLayers: Set<LayerName>
}

// Extra datum types for intel layers
interface ExtendedRingDatum {
    lat: number; lng: number; color: string; size: number
    isCore: boolean; isSelected: boolean
    layerType: string
    id: string
    entity: MapEntity
    dimmed: boolean
}

interface ExtendedArcDatum {
    startLat: number; startLng: number
    endLat: number; endLng: number
    color: [string, string]
    stroke: number
    startId: string
    endId: string
    dimmed: boolean
}

const GlobeView = forwardRef<GlobeViewHandle, GlobeViewProps>(function GlobeView(
    { viewMode, offices, onEntityClick, selectedEntity, intel, chainMatrix, riskConvergence, chokepointAnalysis, activeLayers },
    ref
) {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const globeRef = useRef<any>(null)
    const [hoveredEntityId, setHoveredEntityId] = useState<string | null>(null)

    useImperativeHandle(ref, () => ({
        flyTo(lat: number, lng: number, altitude: number = 1.8) {
            if (globeRef.current) {
                globeRef.current.controls().autoRotate = false
                globeRef.current.pointOfView({ lat, lng, altitude }, 1000)
            }
        },
    }))

    // Initialize globe settings
    useEffect(() => {
        const globe = globeRef.current
        if (!globe) return
        globe.controls().autoRotate = true
        globe.controls().autoRotateSpeed = 0.4
        globe.controls().enableDamping = true
        globe.controls().dampingFactor = 0.1
        globe.pointOfView({ lat: 20, lng: 0, altitude: 2.5 }, 0)
    }, [])

    // Fly to selected entity
    useEffect(() => {
        if (selectedEntity) {
            let lat: number, lng: number;
            if (selectedEntity.type === 'office') { lat = selectedEntity.data.lat; lng = selectedEntity.data.lng; }
            else if (selectedEntity.type === 'risk') { lat = selectedEntity.data.lat; lng = selectedEntity.data.lng; }
            else if (selectedEntity.type === 'regionalRisk') { lat = selectedEntity.data.lat; lng = selectedEntity.data.lng; }
            else if (selectedEntity.type === 'chokepoint') { lat = selectedEntity.data.lat; lng = selectedEntity.data.lng; }
            else if (selectedEntity.type === 'supplier') { lat = selectedEntity.data.lat; lng = selectedEntity.data.lng; }
            else if (selectedEntity.type === 'customer') { lat = selectedEntity.data.lat; lng = selectedEntity.data.lng; }
            else return;

            if (globeRef.current) {
                globeRef.current.controls().autoRotate = false
                globeRef.current.pointOfView(
                    { lat, lng, altitude: 1.8 },
                    1000
                )
            }
        }
    }, [selectedEntity])

    const handleGlobeClick = useCallback(() => {
        onEntityClick(null)
        if (globeRef.current) {
            globeRef.current.controls().autoRotate = true
        }
    }, [onEntityClick])

    const [countriesLineData, setCountriesLineData] = useState<object[]>([])

    useEffect(() => {
        let mounted = true
        const baseUrl = import.meta.env.BASE_URL.replace(/\/$/, '');
        fetchTextOrThrow(`${baseUrl}/data/countries.json`)
            .then(res => {
                if (mounted && res) {
                    const parsed = JSON.parse(res)
                    const features = parsed.features || []
                    setCountriesLineData(features.filter((d: any) => d.properties.ISO_A2 !== 'AQ'))
                }
            })
            .catch(err => console.error("Failed to load country polygons:", err))
        return () => { mounted = false }
    }, [])

    // Helper: Generate Entity IDs
    // Offices: use office.id (from App)
    // Global Layers: use index-based stable IDs (e.g. 'rr-0', 'cp-0')
    // Intel Layers: use index-based stable IDs (e.g. 'sc-0', 'cu-0')

    // Prepare Adjacency Map for Hover Logic
    const adjacencyMap = useMemo(() => {
        const map = new Map<string, Set<string>>()
        const addLink = (a: string, b: string) => {
            if (!map.has(a)) map.set(a, new Set())
            if (!map.has(b)) map.set(b, new Set())
            map.get(a)!.add(b)
            map.get(b)!.add(a)
        }

        // Global Chain
        if (chainMatrix) {
            // Need Ticker -> Office ID map
            const tickerToId = new Map<string, string>()
            offices.forEach(o => {
                if (o.type === 'headquarters' && o.companyId) {
                    tickerToId.set(o.companyId, o.id)
                }
            })

            chainMatrix.dependencies.forEach(dep => {
                const fromId = tickerToId.get(dep.from)
                const toId = tickerToId.get(dep.to)
                if (fromId && toId) addLink(fromId, toId)
            })
        }

        // Intel Chain (HQ <-> Node)
        if (intel) {
            const hq = offices.find(o => o.type === 'headquarters')
            const hqId = hq?.id || 'hq-fallback'

            // Supply Chain
            intel.supplyChain.forEach((_, i) => addLink(hqId, `sc-${i}`))
            // Customers
            intel.customerConcentration.forEach((_, i) => addLink(hqId, `cu-${i}`))
        }

        return map
    }, [chainMatrix, intel, offices])

    // ===== Compute rings data combining all active layers =====
    const ringsData = useMemo((): ExtendedRingDatum[] => {
        const allRings: ExtendedRingDatum[] = []

        // Helper to check if dimmed
        const isDimmed = (id: string) => {
            if (!hoveredEntityId) return false
            if (hoveredEntityId === id) return false
            const neighbors = adjacencyMap.get(hoveredEntityId)
            if (neighbors && neighbors.has(id)) return false
            return true
        }

        // Office rings
        if (activeLayers.has('offices')) {
            offices.forEach((office) => {
                const size = OFFICE_TYPE_SIZES[office.type] || 0.5
                const color = OFFICE_TYPE_COLORS[office.type] || '#6b7280'
                const isSelected = selectedEntity?.type === 'office' && (selectedEntity.data as Office).id === office.id
                const id = office.id

                allRings.push({
                    lat: office.lat, lng: office.lng, color, size,
                    isSelected: false, isCore: true,
                    layerType: 'office', id, entity: { type: 'office', data: office },
                    dimmed: isDimmed(id)
                })
                allRings.push({
                    lat: office.lat, lng: office.lng, color, size,
                    isSelected, isCore: false,
                    layerType: 'office', id, entity: { type: 'office', data: office },
                    dimmed: isDimmed(id)
                })
            })
        }

        if (intel) {
            // Supply chain rings
            if (activeLayers.has('supplyChain')) {
                intel.supplyChain.forEach((node, i) => {
                    const id = `sc-${i}`
                    const color = CRITICALITY_COLORS[node.criticality] || '#6b7280'
                    const isSelected = selectedEntity?.type === 'supplier' && selectedEntity.data === node

                    allRings.push({
                        lat: node.lat, lng: node.lng, color, size: 0.8,
                        isCore: true, isSelected: false,
                        layerType: 'supplyChain', id, entity: { type: 'supplier', data: node },
                        dimmed: isDimmed(id)
                    })
                    allRings.push({
                        lat: node.lat, lng: node.lng, color, size: 0.8,
                        isCore: false, isSelected, // Pulsing is selection or just ambient? Ambient usually. Selection makes it bright.
                        layerType: 'supplyChain', id, entity: { type: 'supplier', data: node },
                        dimmed: isDimmed(id)
                    })
                })
            }

            // Customer rings
            if (activeLayers.has('customers')) {
                intel.customerConcentration.forEach((cust, i) => {
                    const id = `cu-${i}`
                    const color = '#06b6d4'
                    const isSelected = selectedEntity?.type === 'customer' && selectedEntity.data === cust

                    allRings.push({
                        lat: cust.lat, lng: cust.lng, color, size: 0.9,
                        isCore: true, isSelected: false,
                        layerType: 'customer', id, entity: { type: 'customer', data: cust },
                        dimmed: isDimmed(id)
                    })
                    allRings.push({
                        lat: cust.lat, lng: cust.lng, color, size: 0.9,
                        isCore: false, isSelected,
                        layerType: 'customer', id, entity: { type: 'customer', data: cust },
                        dimmed: isDimmed(id)
                    })
                })
            }

            // Risk rings (Intel specific risks)
            if (activeLayers.has('risks')) {
                intel.geopoliticalRisks.forEach((risk, i) => {
                    const id = `rk-${i}`
                    const color = RISK_COLORS[risk.riskScore] || '#f59e0b'
                    const isSelected = selectedEntity?.type === 'risk' && selectedEntity.data === risk

                    allRings.push({
                        lat: risk.lat, lng: risk.lng, color, size: risk.riskScore * 0.8,
                        isCore: true, isSelected: false,
                        layerType: 'risk', id, entity: { type: 'risk', data: risk },
                        dimmed: isDimmed(id)
                    })
                    allRings.push({
                        lat: risk.lat, lng: risk.lng, color, size: risk.riskScore * 0.8,
                        isCore: false, isSelected,
                        layerType: 'risk', id, entity: { type: 'risk', data: risk },
                        dimmed: isDimmed(id)
                    })
                })
            }
        }

        // Global Analysis Layers - ONLY IN GLOBAL VIEW
        if (viewMode === 'global') {
            if (activeLayers.has('risks') && riskConvergence) {
                riskConvergence.regions.forEach((risk, i) => {
                    const id = `rr-${i}`
                    const color = RISK_COLORS[Math.round(risk.overallScore)] || '#f59e0b'
                    const isSelected = selectedEntity?.type === 'regionalRisk' && selectedEntity.data === risk

                    allRings.push({
                        lat: risk.lat, lng: risk.lng, color, size: risk.overallScore * 1.2,
                        isCore: true, isSelected: false,
                        layerType: 'regionalRisk', id, entity: { type: 'regionalRisk', data: risk },
                        dimmed: isDimmed(id)
                    })
                    allRings.push({
                        lat: risk.lat, lng: risk.lng, color, size: risk.overallScore * 1.2,
                        isCore: false, isSelected,
                        layerType: 'regionalRisk', id, entity: { type: 'regionalRisk', data: risk },
                        dimmed: isDimmed(id)
                    })
                })
            }

            if (activeLayers.has('chokepoints') && chokepointAnalysis) {
                chokepointAnalysis.chokepoints.forEach((cp, i) => {
                    const id = `cp-${i}`
                    const color = '#ef4444'
                    const isSelected = selectedEntity?.type === 'chokepoint' && selectedEntity.data === cp

                    allRings.push({
                        lat: cp.lat, lng: cp.lng, color, size: 1.5,
                        isCore: true, isSelected: false,
                        layerType: 'chokepoint', id, entity: { type: 'chokepoint', data: cp },
                        dimmed: isDimmed(id)
                    })
                    allRings.push({
                        lat: cp.lat, lng: cp.lng, color, size: 1.5,
                        isCore: false, isSelected,
                        layerType: 'chokepoint', id, entity: { type: 'chokepoint', data: cp },
                        dimmed: isDimmed(id)
                    })
                })
            }
        }

        return allRings
    }, [offices, selectedEntity, intel, riskConvergence, chokepointAnalysis, activeLayers, viewMode, hoveredEntityId, adjacencyMap])

    // ===== Compute arcs combining all active layers =====
    const arcsData = useMemo((): ExtendedArcDatum[] => {
        const allArcs: ExtendedArcDatum[] = []

        // Helper to check if dimmed
        const isDimmed = (startId: string, endId: string) => {
            if (!hoveredEntityId) return false
            if (hoveredEntityId === startId || hoveredEntityId === endId) return false
            // If hovering an arc (not implemented yet, but if we did), logic would be here.
            return true
        }

        // Office arcs: HQ → other offices
        // Currently offices don't have explicit arcs in design, but let's keep existing logic
        if (activeLayers.has('offices')) {
            const hq = offices.find((o) => o.type === 'headquarters')
            if (hq) {
                offices
                    .filter((o) => o.type !== 'headquarters')
                    .forEach((o) => {
                        allArcs.push({
                            startLat: hq.lat, startLng: hq.lng,
                            endLat: o.lat, endLng: o.lng,
                            color: [
                                OFFICE_TYPE_COLORS.headquarters + '33',
                                (OFFICE_TYPE_COLORS[o.type] || '#6b7280') + '33',
                            ],
                            startId: hq.id, endId: o.id,
                            dimmed: isDimmed(hq.id, o.id),
                            stroke: 0.35,
                        })
                    })
            }
        }

        if (intel) {
            const hq = offices.find((o) => o.type === 'headquarters')
            const hqLat = hq?.lat ?? intel.offices.find(o => o.type === 'headquarters')?.lat ?? 0
            const hqLng = hq?.lng ?? intel.offices.find(o => o.type === 'headquarters')?.lng ?? 0
            const hqId = hq?.id || 'hq-fallback'

            // Supply chain arcs
            if (activeLayers.has('supplyChain')) {
                intel.supplyChain.forEach((node, i) => {
                    const id = `sc-${i}`
                    const nodeColor = CRITICALITY_COLORS[node.criticality] || '#57534e'
                    // Gradient: HQ (Ink) -> Supplier (Criticality Color)
                    // Start opacity 0.5 -> End opacity 0.8 to emphasize the destination
                    const startColor = OFFICE_TYPE_COLORS.headquarters + '80' // 50% opacity
                    const endColor = nodeColor + 'cc' // 80% opacity

                    allArcs.push({
                        startLat: hqLat, startLng: hqLng,
                        endLat: node.lat, endLng: node.lng,
                        color: [startColor, endColor],
                        startId: hqId, endId: id,
                        dimmed: isDimmed(hqId, id),
                        stroke: 0.35,
                    })
                })
            }

            // Customer arcs
            if (activeLayers.has('customers')) {
                intel.customerConcentration.forEach((cust, i) => {
                    const id = `cu-${i}`
                    // Gradient: HQ (Ink) -> Customer (Cyan)
                    const startColor = OFFICE_TYPE_COLORS.headquarters + '80'
                    const endColor = '#06b6d4cc'

                    allArcs.push({
                        startLat: hqLat, startLng: hqLng,
                        endLat: cust.lat, endLng: cust.lng,
                        color: [startColor, endColor],
                        startId: hqId, endId: id,
                        stroke: 0.35,
                        dimmed: false
                    })
                })
            }
        }

        // Global Chain Arcs - ONLY IN GLOBAL VIEW (or if chain layer active, which is managed by App)
        // If viewMode is company, 'chain' might be active to show neighbors, but user asked to reduce noise.
        // Let's stick to activeLayers. App manages activeLayers based on viewMode.
        if (activeLayers.has('chain') && chainMatrix) {
            // Map company ticker to HQ location and ID
            const tickerToData = new Map<string, { lat: number, lng: number, id: string }>()
            offices.forEach(o => {
                if (o.type === 'headquarters' && o.companyId) {
                    tickerToData.set(o.companyId, { lat: o.lat, lng: o.lng, id: o.id })
                }
            })

            chainMatrix.dependencies.forEach(dep => {
                const fromData = tickerToData.get(dep.from)
                const toData = tickerToData.get(dep.to)

                if (fromData && toData) {
                    const isCritical = dep.strength === 'critical';
                    allArcs.push({
                        startLat: fromData.lat, startLng: fromData.lng,
                        endLat: toData.lat, endLng: toData.lng,
                        color: isCritical
                            ? ['#ef4444aa', '#ef444455']
                            : ['#1a1a1a66', '#1a1a1a33'],
                        startId: fromData.id, endId: toData.id,
                        dimmed: isDimmed(fromData.id, toData.id),
                        stroke: 0.35,
                    })
                }
            })
        }

        return allArcs
    }, [offices, intel, chainMatrix, activeLayers, hoveredEntityId])

    // ===== Compute interactive HTML overlay nodes for intel layers =====
    // Reusing the same ID scheme
    const htmlNodesData = useMemo((): IntelNodeDatum[] => {
        const nodes: IntelNodeDatum[] = []

        if (activeLayers.has('offices')) {
            offices.forEach((office) => {
                nodes.push({
                    lat: office.lat, lng: office.lng,
                    layerType: 'office',
                    label: office.city,
                    sublabel: office.country,
                    detail: `${(office.type || '').replace(/_/g, ' ')}`,
                    color: OFFICE_TYPE_COLORS[office.type] || '#1a1a1a',
                    id: office.id,
                    entity: { type: 'office', data: office }
                })
            })
        }

        if (intel) {
            if (activeLayers.has('supplyChain')) {
                intel.supplyChain.forEach((node, i) => {
                    nodes.push({
                        lat: node.lat, lng: node.lng,
                        layerType: 'supplyChain',
                        label: node.entity,
                        sublabel: `${node.city}, ${node.country}`,
                        detail: `${node.role.replace(/_/g, ' ')} · ${node.criticality}`,
                        color: CRITICALITY_COLORS[node.criticality] || '#6b7280',
                        id: `sc-${i}`,
                        entity: { type: 'supplier', data: node }
                    })
                })
            }

            if (activeLayers.has('customers')) {
                intel.customerConcentration.forEach((cust, i) => {
                    nodes.push({
                        lat: cust.lat, lng: cust.lng,
                        layerType: 'customer',
                        label: cust.customer,
                        sublabel: `${cust.hqCity}, ${cust.hqCountry}`,
                        detail: `Revenue share: ${cust.revenueShare}`,
                        color: '#06b6d4',
                        id: `cu-${i}`,
                        entity: { type: 'customer', data: cust }
                    })
                })
            }

            if (activeLayers.has('risks')) {
                intel.geopoliticalRisks.forEach((risk, i) => {
                    nodes.push({
                        lat: risk.lat, lng: risk.lng,
                        layerType: 'risk',
                        label: risk.riskLabel,
                        sublabel: risk.region,
                        detail: `Risk ${risk.riskScore}/5 · ${risk.impactLevel}`,
                        color: RISK_COLORS[risk.riskScore] || '#f59e0b',
                        id: `rk-${i}`,
                        entity: { type: 'risk', data: risk }
                    })
                })
            }
        }

        if (viewMode === 'global') {
            if (activeLayers.has('risks') && riskConvergence) {
                riskConvergence.regions.forEach((risk, i) => {
                    nodes.push({
                        lat: risk.lat, lng: risk.lng,
                        layerType: 'regionalRisk',
                        label: `Regional Risk: ${risk.region}`,
                        sublabel: `${risk.contributingCompanies.length} companies exposed`,
                        detail: `Aggregate Score: ${risk.overallScore}/10`,
                        color: RISK_COLORS[Math.round(risk.overallScore)] || '#f59e0b',
                        id: `rr-${i}`,
                        entity: { type: 'regionalRisk', data: risk }
                    })
                })
            }

            if (activeLayers.has('chokepoints') && chokepointAnalysis) {
                chokepointAnalysis.chokepoints.forEach((cp, i) => {
                    nodes.push({
                        lat: cp.lat, lng: cp.lng,
                        layerType: 'chokepoint',
                        label: `Chokepoint: ${cp.name}`,
                        sublabel: cp.location,
                        detail: `${cp.severity.toUpperCase()} SEVERITY · ${cp.exposedCompanies.length} companies`,
                        color: '#ef4444',
                        id: `cp-${i}`,
                        entity: { type: 'chokepoint', data: cp }
                    })
                })
            }
        }

        return nodes
    }, [intel, activeLayers, offices, riskConvergence, chokepointAnalysis, viewMode, hoveredEntityId, adjacencyMap])

    // Build an HTML element for each intel node overlay
    const handleHtmlElement = useCallback((d: object) => {
        const node = d as IntelNodeDatum
        const wrapper = document.createElement('div')
        wrapper.className = `intel-node-marker type-${node.layerType}`
        wrapper.style.cssText = `--node-color: ${node.color};`
        wrapper.setAttribute('data-id', node.id)

        // Handle dimming via CSS class managed by re-render? No, htmlElement is called once?
        // react-globe.gl updates htmlElement when data changes.
        // But re-creating DOM nodes is expensive.
        // Better to use `onHtmlElementClick` etc? No.
        // Actually, let's rely on rings for dimming visual. HTML markers can stay bright or we can add class.
        // Since we are regenerating the array, `react-globe.gl` might re-render.
        // But `htmlTransitionDuration={0}` will make it instant.

        // Add dimmed class if needed (not passed in Datum, I missed it).
        // Let's assume HTML markers are small and don't need dimming as much as rings/arcs.
        // Or I can add `dimmed` to `IntelNodeDatum`.

        const dot = document.createElement('div')
        dot.className = `intel-node-dot type-${node.layerType}`
        wrapper.appendChild(dot)

        const tooltip = document.createElement('div')
        tooltip.className = 'intel-node-tooltip'
        tooltip.innerHTML = `
            <div class="intel-tt-label">${node.label}</div>
            <div class="intel-tt-sublabel">${node.sublabel}</div>
            <div class="intel-tt-detail">${node.detail}</div>
        `
        wrapper.appendChild(tooltip)

        // Events
        wrapper.addEventListener('click', (e) => {
            e.stopPropagation()
            onEntityClick(node.entity)
            if (globeRef.current) {
                globeRef.current.controls().autoRotate = false
                globeRef.current.pointOfView({ lat: node.lat, lng: node.lng, altitude: 1.8 }, 1000)
            }
        })

        wrapper.addEventListener('mouseenter', () => {
            setHoveredEntityId(node.id)
        })

        wrapper.addEventListener('mouseleave', () => {
            setHoveredEntityId(null)
        })

        return wrapper
    }, [onEntityClick])

    return (
        <Globe
            ref={globeRef}
            rendererConfig={{ alpha: true, antialias: true, powerPreference: "high-performance" }}
            globeMaterial={new THREE.MeshStandardMaterial({
                color: '#eae7d4',
                emissive: '#fdfcf0',
                emissiveIntensity: 0.1,
                transparent: true,
                opacity: 0.95,
                roughness: 0.85,
                metalness: 0.05,
            })}
            showAtmosphere={false}
            backgroundColor="rgba(0,0,0,0)"

            hexPolygonsData={countriesLineData}
            hexPolygonResolution={4}
            hexPolygonMargin={0.5}
            hexPolygonColor={() => 'rgba(26, 26, 26, 0.35)'}
            hexPolygonAltitude={0.005}

            onGlobeClick={handleGlobeClick}

            arcsData={arcsData}
            arcColor={(d: object) => {
                const arc = d as ExtendedArcDatum
                if (arc.dimmed) return ['rgba(0,0,0,0.05)', 'rgba(0,0,0,0.05)']
                return arc.color
            }}
            arcDashLength={0.5}
            arcDashGap={0.5}
            arcDashAnimateTime={2000}
            arcStroke={0.35}
            arcAltitudeAutoScale={0.5}
            // arcTransitionDuration={0} // Instant update

            ringsData={ringsData}
            ringColor={(d: object) => (t: number) => {
                const ring = d as ExtendedRingDatum
                if (ring.dimmed) return ring.color + '11' // Very faint
                if (ring.isCore) return ring.color
                return `${ring.color}${Math.round((1 - t) * 60).toString(16).padStart(2, '0')}`
            }}
            ringAltitude={0.015}
            ringMaxRadius={(d: object) => {
                const ring = d as ExtendedRingDatum
                if (ring.isCore) return ring.size * 0.4
                if (ring.layerType === 'risk' || ring.layerType === 'regionalRisk') {
                    return ring.size * 2.5
                }
                return ring.size * 1.5
            }}
            ringPropagationSpeed={(d: object) => {
                const ring = d as ExtendedRingDatum
                if (ring.isCore) return 0
                return 0.4
            }}
            ringRepeatPeriod={(d: object) => {
                const ring = d as ExtendedRingDatum
                if (ring.isCore) return 0
                return 3000 + Math.random() * 1000
            }}

            htmlElementsData={htmlNodesData}
            htmlElement={handleHtmlElement}
            htmlAltitude={0.015}
            htmlTransitionDuration={0}

            animateIn={true}
            waitForGlobeReady={true}
        />
    )
})

export default GlobeView
