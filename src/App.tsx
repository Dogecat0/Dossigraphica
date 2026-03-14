import { useMemo, useCallback, useRef, useEffect, useState } from 'react'
import GlobeView from './components/Globe'
import type { GlobeViewHandle } from './components/Globe'
import OfficePopup from './components/OfficePopup'
import Header from './components/Header'
import LayerToggle from './components/LayerToggle'
import IntelPanel from './components/IntelPanel'
import companiesData from './data/companies.json'
import { useGeoIntel } from './useGeoIntel'
import type { Company, Office, LayerName } from './types'
import { PanelRightClose, PanelRightOpen, X } from 'lucide-react'

const companies = companiesData as Company[]

export default function App() {
    const {
        selectedCompany,
        selectedOfficeId,
        setSelectedOfficeId,
        registerFlyToCallback,
        isIntelPanelOpen,
        setIsIntelPanelOpen,
        isIntelMinimized,
        setIsIntelMinimized,
        fetchGeoIntelData,
        geoIntelligence,
        intelLoading,
        intelError,
        intelMarkdownContent
    } = useGeoIntel()

    // UI state that doesn't need to be in the global intel store right now
    const [activeLayers, setActiveLayers] = useState<Set<LayerName>>(new Set(['offices']))

    const globeRef = useRef<GlobeViewHandle>(null)

    // Set initial company
    useEffect(() => {
        if (!selectedCompany && companies.length > 0) {
            useGeoIntel.getState().setSelectedCompany(companies[0])
        }
    }, [selectedCompany])

    const currentCompany = selectedCompany || companies[0]

    // Fetch Intel data when company changes
    useEffect(() => {
        if (currentCompany) {
            fetchGeoIntelData(currentCompany.ticker)
            const hq = currentCompany.offices.find(o => o.type === 'headquarters') || currentCompany.offices[0]
            if (hq && globeRef.current) {
                globeRef.current.flyTo(hq.lat, hq.lng, 2.0)
            }
        }
    }, [currentCompany, fetchGeoIntelData])

    // Register the flyTo callback so the Zustand store can control the globe camera
    useEffect(() => {
        registerFlyToCallback((lat, lng, altitude) => {
            globeRef.current?.flyTo(lat, lng, altitude)
        })
    }, [registerFlyToCallback])

    // Flatten offices: merge base company offices with intel offices if available
    const offices = useMemo((): Office[] => {
        if (!currentCompany) return []
        const baseOffices = currentCompany.offices.map((office) => ({
            ...office,
            companyId: currentCompany.company,
        }))

        if (geoIntelligence?.offices) {
            const intelOffices = geoIntelligence.offices.map((office) => ({
                ...office,
                companyId: currentCompany.company,
            }))

            // simple merge, preferring intel offices
            const merged = [...intelOffices]
            baseOffices.forEach(bo => {
                if (!merged.find(io => io.id === bo.id)) {
                    merged.push(bo)
                }
            })
            return merged
        }
        return baseOffices
    }, [currentCompany, geoIntelligence])

    const selectedOffice = useMemo((): Office | null => {
        if (!selectedOfficeId) return null
        return offices.find(o => o.id === selectedOfficeId) || null
    }, [selectedOfficeId, offices])

    const handleOfficeClick = useCallback((office: Office | null) => {
        setSelectedOfficeId(office?.id || null)
    }, [setSelectedOfficeId])

    const handleClosePopup = useCallback(() => {
        setSelectedOfficeId(null)
    }, [setSelectedOfficeId])

    const handleToggleIntel = useCallback(() => {
        setIsIntelPanelOpen(!isIntelPanelOpen)
    }, [isIntelPanelOpen, setIsIntelPanelOpen])

    const handleLayerToggle = useCallback((layer: LayerName) => {
        setActiveLayers(prev => {
            const next = new Set(prev)
            if (next.has(layer)) {
                next.delete(layer)
            } else {
                next.add(layer)
            }
            return next
        })
    }, [])

    const handleIntelNavigate = useCallback((lat: number, lng: number) => {
        globeRef.current?.flyTo(lat, lng)
    }, [])

    return (
        <div className="flex h-screen w-screen overflow-hidden bg-[var(--color-bg-paper)]">
            {/* Main Map Area */}
            <div className="relative flex-1 min-w-0 flex flex-col transition-all duration-500 ease-in-out">
                {/* Header */}
                <Header
                    companyName={currentCompany?.company ?? ''}
                    officeCount={offices.length}
                    companies={companies}
                    hasIntel={!!geoIntelligence && !intelError}
                    intelOpen={isIntelPanelOpen}
                    onToggleIntel={handleToggleIntel}
                    intelLoading={intelLoading}
                />

                {/* 3D Globe */}
                <div className="flex-1 relative scene-container">
                    <GlobeView
                        ref={globeRef}
                        offices={offices}
                        onOfficeClick={handleOfficeClick}
                        selectedOffice={selectedOffice}
                        intel={geoIntelligence}
                        activeLayers={activeLayers}
                    />
                </div>

                {/* Office Popup */}
                <OfficePopup
                    office={selectedOffice}
                    company={currentCompany}
                    onClose={handleClosePopup}
                />

                {/* Layer Toggle */}
                {!isIntelPanelOpen && (
                    <LayerToggle
                        activeLayers={activeLayers}
                        onToggle={handleLayerToggle}
                        hasIntel={geoIntelligence !== null}
                    />
                )}

                {/* Attribution */}
                <div className="absolute bottom-2 left-4 z-30">
                    <p className="text-[10px] text-[var(--color-ink-muted)] opacity-50 font-mono">
                        GLOBE DATA © OPENSTREETMAP · DOSSIGRAPHICA PROJECT 2026
                    </p>
                </div>
            </div>

            {/* Bookmark Strip (Visible when Intel Panel is open but minimized, or just open) */}
            {isIntelPanelOpen && (
                <div className="bookmark-strip border-l border-[var(--color-ink)]">
                    <button
                        onClick={() => setIsIntelMinimized(!isIntelMinimized)}
                        className="bookmark-icon mt-4"
                        title={isIntelMinimized ? "Expand Dossier" : "Minimize Dossier"}
                    >
                        {isIntelMinimized ? <PanelRightOpen size={20} /> : <PanelRightClose size={20} />}
                    </button>
                    <div className="flex-1" />
                    <button
                        onClick={() => setIsIntelPanelOpen(false)}
                        className="bookmark-icon mb-6"
                        title="Close Dossier"
                    >
                        <X size={20} />
                    </button>
                </div>
            )}

            {/* Intel Panel (Dossier) */}
            {isIntelPanelOpen && !isIntelMinimized && (
                <div className="w-[480px] h-full flex flex-col dossier-panel animate-slide-open overflow-hidden">
                    <IntelPanel
                        intel={geoIntelligence}
                        loading={intelLoading}
                        error={intelError}
                        markdown={intelMarkdownContent}
                        onClose={handleToggleIntel}
                        onNavigate={handleIntelNavigate}
                    />
                </div>
            )}
        </div>
    )
}

