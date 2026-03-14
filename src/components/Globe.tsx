import { useRef, useEffect, useState, useMemo, useCallback, useImperativeHandle, forwardRef } from 'react'
import * as THREE from 'three'
import Globe from 'react-globe.gl'
import { fetchTextOrThrow } from '../utils/fetchTextOrThrow'
import type {
    Office, OfficeType, RingDatum, ArcDatum,
    GeoIntelligence, LayerName, SupplyChainNode, CustomerNode, GeopoliticalRisk
} from '../types'

const OFFICE_TYPE_COLORS: Record<OfficeType, string> = {
    headquarters: '#1a1a1a',
    regional: '#4a4a4a',
    engineering: '#4a4a4a',
    satellite: '#8a8a8a',
    manufacturing: '#a36633',
    data_center: '#2a5a8a',
    sales: '#3d6a4a',
    logistics: '#a33333',
}

const OFFICE_TYPE_SIZES: Record<OfficeType, number> = {
    headquarters: 1.5,
    regional: 0.9,
    engineering: 0.8,
    satellite: 0.6,
    manufacturing: 1.1,
    data_center: 1.0,
    sales: 0.8,
    logistics: 0.9,
}

const CRITICALITY_COLORS: Record<string, string> = {
    critical: '#a33333',
    important: '#a36633',
    standard: '#4a4a4a',
}

const RISK_COLORS: Record<number, string> = {
    1: '#3d6a4a',
    2: '#5d8a6a',
    3: '#b08d57',
    4: '#a36633',
    5: '#a33333',
}

export interface GlobeViewHandle {
    flyTo: (lat: number, lng: number, altitude?: number) => void
}

interface IntelNodeDatum {
    lat: number
    lng: number
    layerType: 'office' | 'supplyChain' | 'customer' | 'risk'
    label: string
    sublabel: string
    detail: string
    color: string
    id: string
    rawRef?: any
}

interface GlobeViewProps {
    offices: Office[]
    onOfficeClick: (office: Office | null) => void
    selectedOffice: Office | null
    intel: GeoIntelligence | null
    activeLayers: Set<LayerName>
}

// Extra datum types for intel layers
interface SupplyChainRingDatum {
    lat: number; lng: number; color: string; size: number
    isCore: boolean; isSelected: boolean
    layerType: 'supplyChain'
    ref: SupplyChainNode
}

interface CustomerRingDatum {
    lat: number; lng: number; color: string; size: number
    isCore: boolean; isSelected: boolean
    layerType: 'customer'
    ref: CustomerNode
}

interface RiskRingDatum {
    lat: number; lng: number; color: string; size: number
    isCore: boolean; isSelected: boolean
    layerType: 'risk'
    ref: GeopoliticalRisk
}

type AllRingDatum = RingDatum | SupplyChainRingDatum | CustomerRingDatum | RiskRingDatum

const GlobeView = forwardRef<GlobeViewHandle, GlobeViewProps>(function GlobeView(
    { offices, onOfficeClick, selectedOffice, intel, activeLayers },
    ref
) {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const globeRef = useRef<any>(null)


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

    // Fly to selected office
    useEffect(() => {
        if (selectedOffice && globeRef.current) {
            globeRef.current.controls().autoRotate = false
            globeRef.current.pointOfView(
                { lat: selectedOffice.lat, lng: selectedOffice.lng, altitude: 1.8 },
                1000
            )
        }
    }, [selectedOffice])

    const handleGlobeClick = useCallback(() => {
        onOfficeClick(null)
        if (globeRef.current) {
            globeRef.current.controls().autoRotate = true
        }
    }, [onOfficeClick])

    const [countriesLineData, setCountriesLineData] = useState<object[]>([])

    useEffect(() => {
        let mounted = true
        fetchTextOrThrow('public/data/countries.json')
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

    // ===== Compute rings data combining all active layers =====
    const ringsData = useMemo((): AllRingDatum[] => {
        const allRings: AllRingDatum[] = []

        // Office rings
        if (activeLayers.has('offices')) {
            offices.forEach((office) => {
                const size = OFFICE_TYPE_SIZES[office.type] || 0.5
                const color = OFFICE_TYPE_COLORS[office.type] || '#6b7280'
                const isSelected = selectedOffice?.id === office.id

                allRings.push({
                    lat: office.lat, lng: office.lng, color, size,
                    isSelected: false, isCore: true, officeRef: office,
                })
                allRings.push({
                    lat: office.lat, lng: office.lng, color, size,
                    isSelected, isCore: false, officeRef: office,
                })
            })
        }

        if (!intel) return allRings

        // Supply chain rings
        if (activeLayers.has('supplyChain')) {
            intel.supplyChain.forEach((node) => {
                const color = CRITICALITY_COLORS[node.criticality] || '#6b7280'
                // Core dot
                allRings.push({
                    lat: node.lat, lng: node.lng, color, size: 0.8,
                    isCore: true, isSelected: false,
                    layerType: 'supplyChain', ref: node,
                } as SupplyChainRingDatum)
                // Pulsing ring
                allRings.push({
                    lat: node.lat, lng: node.lng, color, size: 0.8,
                    isCore: false, isSelected: false,
                    layerType: 'supplyChain', ref: node,
                } as SupplyChainRingDatum)
            })
        }

        // Customer rings
        if (activeLayers.has('customers')) {
            intel.customerConcentration.forEach((cust) => {
                const color = '#06b6d4'
                allRings.push({
                    lat: cust.lat, lng: cust.lng, color, size: 0.9,
                    isCore: true, isSelected: false,
                    layerType: 'customer', ref: cust,
                } as CustomerRingDatum)
                allRings.push({
                    lat: cust.lat, lng: cust.lng, color, size: 0.9,
                    isCore: false, isSelected: false,
                    layerType: 'customer', ref: cust,
                } as CustomerRingDatum)
            })
        }

        // Risk rings (bigger, threat-colored)
        if (activeLayers.has('risks')) {
            intel.geopoliticalRisks.forEach((risk) => {
                const color = RISK_COLORS[risk.riskScore] || '#f59e0b'
                allRings.push({
                    lat: risk.lat, lng: risk.lng, color, size: risk.riskScore * 0.8,
                    isCore: true, isSelected: false,
                    layerType: 'risk', ref: risk,
                } as RiskRingDatum)
                allRings.push({
                    lat: risk.lat, lng: risk.lng, color, size: risk.riskScore * 0.8,
                    isCore: false, isSelected: false,
                    layerType: 'risk', ref: risk,
                } as RiskRingDatum)
            })
        }

        return allRings
    }, [offices, selectedOffice, intel, activeLayers])

    // ===== Compute arcs combining all active layers =====
    const arcsData = useMemo((): ArcDatum[] => {
        const allArcs: ArcDatum[] = []

        // Office arcs: HQ → other offices
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
                        })
                    })
            }
        }

        if (!intel) return allArcs

        // Find HQ for intel arcs
        const hqOffice = offices.find((o) => o.type === 'headquarters')
        const hqLat = hqOffice?.lat ?? intel.offices.find(o => o.type === 'headquarters')?.lat ?? 0
        const hqLng = hqOffice?.lng ?? intel.offices.find(o => o.type === 'headquarters')?.lng ?? 0

        // Supply chain arcs
        if (activeLayers.has('supplyChain')) {
            intel.supplyChain.forEach((node) => {
                const color = CRITICALITY_COLORS[node.criticality] || '#6b7280'
                allArcs.push({
                    startLat: hqLat, startLng: hqLng,
                    endLat: node.lat, endLng: node.lng,
                    color: [color + '55', color + '22'],
                })
            })
        }

        // Customer arcs
        if (activeLayers.has('customers')) {
            intel.customerConcentration.forEach((cust) => {
                allArcs.push({
                    startLat: hqLat, startLng: hqLng,
                    endLat: cust.lat, endLng: cust.lng,
                    color: ['#06b6d455', '#06b6d422'],
                })
            })
        }

        return allArcs
    }, [offices, intel, activeLayers])

    // ===== Compute interactive HTML overlay nodes for intel layers =====
    const htmlNodesData = useMemo((): IntelNodeDatum[] => {
        const nodes: IntelNodeDatum[] = []

        if (activeLayers.has('offices')) {
            offices.forEach((office, i) => {
                nodes.push({
                    lat: office.lat, lng: office.lng,
                    layerType: 'office',
                    label: office.city,
                    sublabel: office.country,
                    detail: `${(office.type || '').replace(/_/g, ' ')}`,
                    color: OFFICE_TYPE_COLORS[office.type] || '#1a1a1a',
                    id: `of-${i}`,
                    rawRef: office,
                })
            })
        }

        if (!intel) return nodes

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
                })
            })
        }

        return nodes
    }, [intel, activeLayers, offices])

    // Build an HTML element for each intel node overlay
    const handleHtmlElement = useCallback((d: object) => {
        const node = d as IntelNodeDatum
        const wrapper = document.createElement('div')
        wrapper.className = 'intel-node-marker'
        wrapper.style.cssText = `--node-color: ${node.color};`
        wrapper.setAttribute('data-id', node.id)

        // Hit target dot
        const dot = document.createElement('div')
        dot.className = 'intel-node-dot'
        wrapper.appendChild(dot)

        // Tooltip
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
            if (node.layerType === 'office' && node.rawRef) {
                onOfficeClick(node.rawRef as Office)
            }
            if (globeRef.current) {
                globeRef.current.controls().autoRotate = false
                globeRef.current.pointOfView({ lat: node.lat, lng: node.lng, altitude: 1.8 }, 1000)
            }
        })

        return wrapper
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [onOfficeClick])

    return (
        <Globe
            ref={globeRef}
            rendererConfig={{ alpha: true, antialias: true, powerPreference: "high-performance" }}
            globeMaterial={new THREE.MeshStandardMaterial({
                color: '#eae7d4', // Darker richer parchment base
                emissive: '#fdfcf0',
                emissiveIntensity: 0.1,
                transparent: true,
                opacity: 0.95,
                roughness: 0.85,
                metalness: 0.05,
            })}
            showAtmosphere={false}
            backgroundColor="rgba(0,0,0,0)"

            // 1. Landmass as stronger ink dots, with better resolution
            hexPolygonsData={countriesLineData}
            hexPolygonResolution={4}
            hexPolygonMargin={0.5}
            hexPolygonColor={() => 'rgba(26, 26, 26, 0.35)'}
            hexPolygonAltitude={0.005}

            onGlobeClick={handleGlobeClick}

            arcsData={arcsData}
            arcColor="color"
            arcDashLength={0.5}
            arcDashGap={0.5}
            arcDashAnimateTime={2000}
            arcStroke={0.35}
            arcAltitudeAutoScale={0.5}

            ringsData={ringsData}
            ringColor={(d: object) => (t: number) => {
                const ring = d as AllRingDatum
                if (ring.isCore) return ring.color
                // Muted ink pulses
                return `${ring.color}${Math.round((1 - t) * 60).toString(16).padStart(2, '0')}`
            }}
            ringAltitude={0.015}
            ringMaxRadius={(d: object) => {
                const ring = d as AllRingDatum
                if (ring.isCore) return ring.size * 0.4
                if ('layerType' in ring && (ring as RiskRingDatum).layerType === 'risk') {
                    return ring.size * 2.5
                }
                return ring.size * 1.5
            }}
            ringPropagationSpeed={(d: object) => {
                const ring = d as AllRingDatum
                if (ring.isCore) return 0
                return 0.4
            }}
            ringRepeatPeriod={(d: object) => {
                const ring = d as AllRingDatum
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
