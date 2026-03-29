import { useRef, useEffect, useState, useMemo, useCallback, useImperativeHandle, forwardRef } from 'react'
import * as THREE from 'three'
import Globe from 'react-globe.gl'
import { fetchTextOrThrow } from '../utils/fetchTextOrThrow'
import { assignStackPositions, getStackOffset } from '../utils/nodeGrouping'
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


const CRITICALITY_COLORS: Record<string, string> = {
    critical: '#92400e',          // Amber-800 — warm earth, distinct from red chokepoints
    important: '#b45309',         // Amber-700
    standard: '#78716c',          // Stone-500
}

// Per-company risk: Cartographic blue (1-5 scale)
const COMPANY_RISK_COLORS: Record<number, string> = {
    1: '#93c5fd', // Blue-300 — minor
    2: '#3b82f6', // Blue-500 — moderate
    3: '#2563eb', // Blue-600 — elevated
    4: '#1d4ed8', // Blue-700 — high
    5: '#1e3a8a', // Blue-900 — critical
}

// Regional risk: Map 1-10 score to 5 visual tiers for maximum differentiation
// Tier 1: 1-2, Tier 2: 3-4, Tier 3: 5-6, Tier 4: 7-8, Tier 5: 9-10
function getRegionalRiskColor(score: number): string {
    const tier = Math.min(5, Math.ceil(score / 2))
    return COMPANY_RISK_COLORS[tier] || '#2563eb'
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
    stackIndex: number
    stackTotal: number
    dimmed: boolean
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

    // Rings layer fully removed — HTML overlay dots handle all node rendering

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
    // Helper: check if a node should be dimmed based on hover adjacency
    const isDimmedNode = useCallback((id: string) => {
        if (!hoveredEntityId) return false
        if (hoveredEntityId === id) return false
        const neighbors = adjacencyMap.get(hoveredEntityId)
        if (neighbors && neighbors.has(id)) return false
        return true
    }, [hoveredEntityId, adjacencyMap])

    const htmlNodesData = useMemo((): IntelNodeDatum[] => {
        // Build raw nodes first (without stack info)
        const rawNodes: Omit<IntelNodeDatum, 'stackIndex' | 'stackTotal' | 'dimmed'>[] = []

        if (activeLayers.has('offices')) {
            offices.forEach((office) => {
                rawNodes.push({
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
                    rawNodes.push({
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
                    rawNodes.push({
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
                    rawNodes.push({
                        lat: risk.lat, lng: risk.lng,
                        layerType: 'risk',
                        label: risk.riskLabel,
                        sublabel: risk.region,
                        detail: `Risk ${risk.riskScore}/5 · ${risk.impactLevel}`,
                        color: COMPANY_RISK_COLORS[risk.riskScore] || '#7c3aed',
                        id: `rk-${i}`,
                        entity: { type: 'risk', data: risk }
                    })
                })
            }
        }

        if (viewMode === 'global') {
            if (activeLayers.has('risks') && riskConvergence) {
                riskConvergence.regions.forEach((risk, i) => {
                    rawNodes.push({
                        lat: risk.lat, lng: risk.lng,
                        layerType: 'regionalRisk',
                        label: `Regional Risk: ${risk.region}`,
                        sublabel: `${risk.contributingCompanies.length} companies exposed`,
                        detail: `Aggregate Score: ${risk.overallScore}/10`,
                        color: getRegionalRiskColor(risk.overallScore),
                        id: `rr-${i}`,
                        entity: { type: 'regionalRisk', data: risk }
                    })
                })
            }

            if (activeLayers.has('chokepoints') && chokepointAnalysis) {
                chokepointAnalysis.chokepoints.forEach((cp, i) => {
                    rawNodes.push({
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

        // Assign stack positions for overlapping nodes, then add dimmed state
        const stacked = assignStackPositions(rawNodes, 0.5)
        return stacked.map(node => ({
            ...node,
            dimmed: isDimmedNode(node.id),
        }))
    }, [intel, activeLayers, offices, riskConvergence, chokepointAnalysis, viewMode, isDimmedNode])

    // Build an HTML element for each intel node overlay
    const handleHtmlElement = useCallback((d: object) => {
        const node = d as IntelNodeDatum
        const wrapper = document.createElement('div')
        wrapper.className = `intel-node-marker type-${node.layerType}${node.dimmed ? ' dimmed' : ''}${node.stackTotal > 1 ? ' stacked' : ''}`
        wrapper.setAttribute('data-id', node.id)

        // Apply screen-space pixel offset for stacked (overlapping) nodes
        const { dx, dy } = getStackOffset(node.stackIndex, node.stackTotal)
        wrapper.style.cssText = `--node-color: ${node.color}; --stack-dx: ${dx}px; --stack-dy: ${dy}px;`

        // Render an SVG shield for regionalRisk, regular dot for everything else
        if (node.layerType === 'regionalRisk') {
            const shield = document.createElementNS('http://www.w3.org/2000/svg', 'svg')
            shield.setAttribute('viewBox', '0 0 24 24')
            shield.setAttribute('width', '22')
            shield.setAttribute('height', '22')
            shield.setAttribute('class', 'intel-node-shield')
            shield.innerHTML = `<path d="M12 2L3 7v5c0 5.55 3.84 10.74 9 12 5.16-1.26 9-6.45 9-12V7L12 2z" fill="${node.color}" stroke="rgba(253,252,240,0.9)" stroke-width="1.5"/>`
            wrapper.appendChild(shield)
        } else {
            const dot = document.createElement('div')
            dot.className = `intel-node-dot type-${node.layerType}`
            wrapper.appendChild(dot)
        }

        // Show count badge on the first node of a stack
        if (node.stackTotal > 1 && node.stackIndex === 0) {
            const badge = document.createElement('div')
            badge.className = 'intel-node-count-badge'
            badge.textContent = `${node.stackTotal}`
            wrapper.appendChild(badge)
        }

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
