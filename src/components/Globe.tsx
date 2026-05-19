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
    headquarters: '#121214',      // Midnight Graphite
    regional: '#76767c',          // Ink Light
    engineering: '#76767c',       // Ink Light
    satellite: '#a8a29e',         // Warm grey
    manufacturing: '#c2593f',     // Critical Rust Orange
    data_center: '#1f486d',       // Accent Blue
    sales: '#2e4d3a',             // Forest Sage
    logistics: '#c2593f',         // Critical Rust Orange
}


const CRITICALITY_COLORS: Record<string, string> = {
    critical: '#c2593f',          // Critical Rust Orange
    important: '#c5a880',         // Brushed Gold
    standard: '#76767c',          // Ink Light
}

// Per-company risk: Gold-to-Rust scale (1-5 scale)
const COMPANY_RISK_COLORS: Record<number, string> = {
    1: '#e4dcc4', // Muted sage/gold
    2: '#c5a880', // Brushed Gold
    3: '#ad8755', // Deeper Gold/Bronze
    4: '#c2593f', // Rust Orange
    5: '#8f331d', // Deep Blood Rust
}

// Regional risk: Map 1-10 score to 5 visual tiers for maximum differentiation
// Tier 1: 1-2, Tier 2: 3-4, Tier 3: 5-6, Tier 4: 7-8, Tier 5: 9-10
function getRegionalRiskColor(score: number): string {
    const tier = Math.min(5, Math.ceil(score / 2))
    return COMPANY_RISK_COLORS[tier] || '#c2593f'
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
    const containerRef = useRef<HTMLDivElement>(null)
    const hasInitializedRef = useRef(false)
    const [hoveredEntityId, setHoveredEntityId] = useState<string | null>(null)
    const [dimensions, setDimensions] = useState({ width: 0, height: 0 })
    const [isVisible, setIsVisible] = useState(false)
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

    useEffect(() => {
        if (!containerRef.current) return
        const observer = new ResizeObserver((entries) => {
            const { width, height } = entries[0].contentRect
            setDimensions({ width, height })
        })
        observer.observe(containerRef.current)
        return () => observer.disconnect()
    }, [])

    useImperativeHandle(ref, () => ({
        flyTo(lat: number, lng: number, altitude: number = 1.8) {
            if (globeRef.current) {
                globeRef.current.controls().autoRotate = false
                globeRef.current.pointOfView({ lat, lng, altitude }, 1000)
            }
        },
    }))

    // Initialize globe settings and safe mobile touch controls
    useEffect(() => {
        if (hasInitializedRef.current) return
        
        const globe = globeRef.current
        if (!globe) return
        
        hasInitializedRef.current = true
        
        const controls = globe.controls()
        controls.autoRotate = true
        controls.autoRotateSpeed = 0.4
        controls.enableDamping = true
        controls.dampingFactor = 0.1
        controls.enableZoom = true
        controls.enableRotate = true
        controls.enablePan = true
        
        // Mobile gesture safeguards: ONE finger for rotation, TWO fingers for dolly zoom/pan
        controls.touches = {
            ONE: THREE.TOUCH.ROTATE,
            TWO: THREE.TOUCH.DOLLY_PAN
        }
        
        // Set camera far away instantly (0ms) then zoom in smoothly
        globe.pointOfView({ lat: 20, lng: 0, altitude: 6.5 }, 0)
        const timer = setTimeout(() => {
            if (globeRef.current) {
                globeRef.current.pointOfView({ lat: 20, lng: 0, altitude: 2.5 }, 2500)
            }
            setIsVisible(true)
        }, 100)

        return () => clearTimeout(timer)
    }, [countriesLineData, dimensions])

    // Add luxury gold graticule coordinate gridlines to the globe scene
    useEffect(() => {
        const globe = globeRef.current
        if (!globe) return
        const scene = globe.scene()
        
        const gridGroup = new THREE.Group()
        gridGroup.name = 'cartographic-graticule'
        
        const radius = 100.08 // Slightly above globe surface (radius 100)
        const gridColor = new THREE.Color('#c5a880')
        const gridMaterial = new THREE.LineBasicMaterial({
            color: gridColor,
            transparent: true,
            opacity: 0.15
        })
        
        // Draw latitude lines (parallels)
        const latitudes = [-75, -60, -45, -30, -15, 0, 15, 30, 45, 60, 75]
        latitudes.forEach(lat => {
            const points: THREE.Vector3[] = []
            const phi = (90 - lat) * Math.PI / 180
            const y = radius * Math.cos(phi)
            const rLat = radius * Math.sin(phi)
            
            for (let i = 0; i <= 72; i++) {
                const theta = (i * 5) * Math.PI / 180
                const x = rLat * Math.sin(theta)
                const z = rLat * Math.cos(theta)
                points.push(new THREE.Vector3(x, y, z))
            }
            
            const geometry = new THREE.BufferGeometry().setFromPoints(points)
            const line = new THREE.Line(geometry, gridMaterial)
            gridGroup.add(line)
        })
        
        // Draw longitude lines (meridians) every 30 degrees
        for (let lon = 0; lon < 360; lon += 30) {
            const points: THREE.Vector3[] = []
            const theta = lon * Math.PI / 180
            
            for (let latDeg = -90; latDeg <= 90; latDeg += 2.5) {
                const phi = (90 - latDeg) * Math.PI / 180
                const x = radius * Math.sin(phi) * Math.sin(theta)
                const y = radius * Math.cos(phi)
                const z = radius * Math.sin(phi) * Math.cos(theta)
                points.push(new THREE.Vector3(x, y, z))
            }
            
            const geometry = new THREE.BufferGeometry().setFromPoints(points)
            const line = new THREE.Line(geometry, gridMaterial)
            gridGroup.add(line)
        }
        
        scene.add(gridGroup)
        
        return () => {
            scene.remove(gridGroup)
            gridGroup.clear()
        }
    }, [])

    // Fly to selected entity
    useEffect(() => {
        if (selectedEntity) {
            let lat: number, lng: number;
            if (selectedEntity.type === 'office') { lat = selectedEntity.data.lat; lng = selectedEntity.data.lng; }
            else if (selectedEntity.type === 'risk') { lat = selectedEntity.data.lat ?? 0; lng = selectedEntity.data.lng ?? 0; }
            else if (selectedEntity.type === 'regionalRisk') { lat = selectedEntity.data.lat; lng = selectedEntity.data.lng; }
            else if (selectedEntity.type === 'chokepoint') { lat = selectedEntity.data.lat; lng = selectedEntity.data.lng; }
            else if (selectedEntity.type === 'supplier') { lat = selectedEntity.data.lat ?? 0; lng = selectedEntity.data.lng ?? 0; }
            else if (selectedEntity.type === 'customer') { lat = selectedEntity.data.lat ?? 0; lng = selectedEntity.data.lng ?? 0; }
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

    // Pause globe rotation on hover and handle robust hover cleanup
    useEffect(() => {
        const container = containerRef.current
        if (!container) return

        const handleMouseEnter = () => {
            if (globeRef.current) {
                globeRef.current.controls().autoRotate = false
            }
        }

        const handleMouseLeave = () => {
            // Robust hover cleanup: unconditionally clear any stuck hover states
            setHoveredEntityId(null)

            // Only resume auto-rotation if no entity popup is active
            if (globeRef.current && !selectedEntity) {
                globeRef.current.controls().autoRotate = true
            }
        }

        container.addEventListener('mouseenter', handleMouseEnter)
        container.addEventListener('mouseleave', handleMouseLeave)

        return () => {
            container.removeEventListener('mouseenter', handleMouseEnter)
            container.removeEventListener('mouseleave', handleMouseLeave)
        }
    }, [selectedEntity])


    const handleGlobeClick = useCallback((_coords: any, event: MouseEvent) => {
        // If the click target is not the canvas (e.g. it is an HTML node marker), ignore it
        if (event && (event.target as HTMLElement).tagName !== 'CANVAS') {
            return
        }

        onEntityClick(null)
        if (globeRef.current) {
            globeRef.current.controls().autoRotate = true
        }
    }, [onEntityClick])


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
                        endLat: node.lat ?? 0, endLng: node.lng ?? 0,
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
                    // Gradient: HQ (Ink) -> Customer (Forest Sage)
                    const startColor = OFFICE_TYPE_COLORS.headquarters + '80'
                    const endColor = '#2e4d3acc'

                    allArcs.push({
                        startLat: hqLat, startLng: hqLng,
                        endLat: cust.lat ?? 0, endLng: cust.lng ?? 0,
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
                            ? ['#c2593faa', '#c2593f55']
                            : ['#c5a88066', '#c5a88033'],
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
                        lat: node.lat ?? 0, lng: node.lng ?? 0,
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
                        lat: cust.lat ?? 0, lng: cust.lng ?? 0,
                        layerType: 'customer',
                        label: cust.customer,
                        sublabel: `${cust.hqCity}, ${cust.hqCountry}`,
                        detail: `Revenue share: ${cust.revenueShare}`,
                        color: '#2e4d3a', // Forest Sage
                        id: `cu-${i}`,
                        entity: { type: 'customer', data: cust }
                    })
                })
            }

            if (activeLayers.has('risks')) {
                intel.geopoliticalRisks.forEach((risk, i) => {
                    rawNodes.push({
                        lat: risk.lat ?? 0, lng: risk.lng ?? 0,
                        layerType: 'risk',
                        label: risk.riskLabel,
                        sublabel: risk.region,
                        detail: `Risk ${risk.riskScore}/5 · ${risk.impactLevel}`,
                        color: COMPANY_RISK_COLORS[risk.riskScore] || '#ad8755',
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
                        color: '#c2593f', // Critical Rust Orange
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
        <div ref={containerRef} className="w-full h-full">
            {dimensions.width > 0 && countriesLineData.length > 0 && (
                <div 
                    className="w-full h-full"
                    style={{ 
                        transition: 'opacity 1.5s cubic-bezier(0.25, 1, 0.5, 1), transform 1.5s cubic-bezier(0.25, 1, 0.5, 1)', 
                        opacity: isVisible ? 1 : 0,
                        transform: isVisible ? 'scale(1)' : 'scale(0.85)'
                    }}
                >
                    <Globe
                        ref={globeRef}
                        width={dimensions.width}
                        height={dimensions.height}
                        rendererConfig={{ alpha: true, antialias: true, powerPreference: "high-performance" }}
            globeMaterial={new THREE.MeshStandardMaterial({
                color: '#e5dec9', // Antique Warm Parchment
                emissive: '#e5dec9', // Subtle warm glow
                emissiveIntensity: 0.05,
                transparent: true,
                opacity: 0.98,
                roughness: 0.85,
                metalness: 0.02,
            })}
            showAtmosphere={false}
            backgroundColor="rgba(0,0,0,0)"

            hexPolygonsData={countriesLineData}
            hexPolygonResolution={4}
            hexPolygonMargin={0.5}
            hexPolygonColor={() => 'rgba(18, 18, 20, 0.15)'} // Charcoal Ink Landmasses
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

            animateIn={false}
            waitForGlobeReady={true}
                    />
                </div>
            )}
        </div>
    )
})

export default GlobeView
