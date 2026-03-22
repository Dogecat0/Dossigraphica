import { useMemo, useCallback, useRef, useEffect, useState } from 'react'
import GlobeView from './components/Globe'
import type { GlobeViewHandle } from './components/Globe'
import EntityPopup from './components/EntityPopup'
import Header from './components/Header'
import LayerToggle from './components/LayerToggle'
import IntelPanel from './components/IntelPanel'
import GlobalPanel from './components/GlobalPanel'
import companiesData from './data/companies.json'
import { useGeoIntel } from './useGeoIntel'
import type { Company, Office, LayerName, MapEntity } from './types'
import { PanelRightClose, PanelRightOpen, X } from 'lucide-react'

const companies = companiesData as Company[]

export default function App() {
    const {
        selectedCompany,
        setSelectedOfficeId,
        registerFlyToCallback,
        isIntelPanelOpen,
        setIsIntelPanelOpen,
        isIntelMinimized,
        setIsIntelMinimized,
        fetchGeoIntelData,
        fetchGlobalAnalysis,
        geoIntelligence,
        chainMatrix,
        riskConvergence,
        chokepointAnalysis,
        intelLoading,
        intelError,
        intelMarkdownContent,
        globalLoading,
        globalError
    } = useGeoIntel()

    const viewMode = selectedCompany ? 'company' : 'global'

    // UI state
    const [activeLayers, setActiveLayers] = useState<Set<LayerName>>(new Set(['chain', 'risks', 'chokepoints', 'offices']))
    const [selectedEntity, setSelectedEntity] = useState<MapEntity | null>(null)
    const [globalTab, setGlobalTab] = useState<'overview' | 'chain' | 'risks' | 'chokepoints'>('overview')

    const globeRef = useRef<GlobeViewHandle>(null)

    // Initial data fetch
    useEffect(() => {
        fetchGlobalAnalysis()
    }, [fetchGlobalAnalysis])

    // Fetch Intel data and adjust layers when company changes
    useEffect(() => {
        if (selectedCompany) {
            fetchGeoIntelData(selectedCompany.ticker)
            // Auto-switch layers for company view
            setActiveLayers(new Set(['offices', 'supplyChain', 'customers', 'risks']))
            setSelectedEntity(null) // Clear selection
            
            // Initial fly-to HQ
            const hq = selectedCompany.offices.find(o => o.type === 'headquarters') || selectedCompany.offices[0]
            if (hq && globeRef.current) {
                globeRef.current.flyTo(hq.lat, hq.lng, 2.0)
            }
        } else {
            // Auto-switch layers for global view
            setActiveLayers(new Set(['chain', 'risks', 'chokepoints', 'offices']))
            setSelectedEntity(null)
            setGlobalTab('overview')
        }
    }, [selectedCompany, fetchGeoIntelData])

    // Handle Global Tab Changes (Dynamic Filtering)
    const handleGlobalTabChange = useCallback((tab: 'overview' | 'chain' | 'risks' | 'chokepoints') => {
        setGlobalTab(tab)
        if (viewMode === 'global') {
            switch (tab) {
                case 'overview':
                    setActiveLayers(new Set(['chain', 'risks', 'chokepoints', 'offices']))
                    break
                case 'chain':
                    setActiveLayers(new Set(['chain', 'offices']))
                    break
                case 'risks':
                    setActiveLayers(new Set(['risks']))
                    break
                case 'chokepoints':
                    setActiveLayers(new Set(['chokepoints']))
                    break
            }
        }
    }, [viewMode])

    // Register the flyTo callback
    useEffect(() => {
        registerFlyToCallback((lat, lng, altitude) => {
            globeRef.current?.flyTo(lat, lng, altitude)
        })
    }, [registerFlyToCallback])

    // Flatten offices: merge base company offices with intel offices if available
    const allOffices = useMemo((): Office[] => {
        const result: Office[] = []
        
        if (viewMode === 'global') {
            // Global View: Show only HQs of all companies
            companies.forEach(comp => {
                const hq = comp.offices.find(o => o.type === 'headquarters')
                if (hq) {
                    result.push({ ...hq, companyId: comp.ticker })
                }
            })
            return result
        }

        // Company View: Show all offices for selected company ONLY
        if (selectedCompany) {
            const compOffices = geoIntelligence?.offices || selectedCompany.offices
            compOffices.forEach(off => {
                result.push({
                    ...off,
                    companyId: selectedCompany.ticker
                })
            })

            // Optional: Show HQs of companies that have a dependency relationship
            if (chainMatrix) {
                const relatedTickers = new Set<string>()
                chainMatrix.dependencies.forEach(dep => {
                    if (dep.from === selectedCompany.ticker) relatedTickers.add(dep.to)
                    if (dep.to === selectedCompany.ticker) relatedTickers.add(dep.from)
                })

                companies.forEach(comp => {
                    if (relatedTickers.has(comp.ticker) && comp.ticker !== selectedCompany.ticker) {
                        const hq = comp.offices.find(o => o.type === 'headquarters')
                        if (hq) result.push({ ...hq, companyId: comp.ticker })
                    }
                })
            }
        }

        return result
    }, [viewMode, selectedCompany, geoIntelligence, chainMatrix])

    // Fix EntityPopup company lookup bug (for offices)
    const popupCompany = useMemo(() => {
        if (!selectedEntity || selectedEntity.type !== 'office') return null
        const office = selectedEntity.data as Office
        if (selectedCompany && office.companyId === selectedCompany.ticker) return selectedCompany
        return companies.find(c => c.ticker === office.companyId) || null
    }, [selectedEntity, selectedCompany])

    const handleEntityClick = useCallback((entity: MapEntity | null) => {
        setSelectedEntity(entity)
        if (entity && entity.type === 'office') {
             setSelectedOfficeId((entity.data as Office).id)
        } else {
             setSelectedOfficeId(null)
        }
    }, [setSelectedOfficeId])

    const handleClosePopup = useCallback(() => {
        setSelectedEntity(null)
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
                    companyName={selectedCompany?.company ?? 'Global Value Chain'}
                    officeCount={allOffices.length}
                    companies={companies}
                    hasIntel={viewMode === 'global' ? !!chainMatrix : (!!geoIntelligence && !intelError)}
                    intelOpen={isIntelPanelOpen}
                    onToggleIntel={handleToggleIntel}
                    intelLoading={viewMode === 'company' ? intelLoading : globalLoading}
                />

                {/* 3D Globe */}
                <div className="flex-1 relative scene-container">
                    <GlobeView
                        ref={globeRef}
                        viewMode={viewMode}
                        offices={allOffices}
                        onEntityClick={handleEntityClick}
                        selectedEntity={selectedEntity}
                        intel={geoIntelligence}
                        chainMatrix={chainMatrix}
                        riskConvergence={riskConvergence}
                        chokepointAnalysis={chokepointAnalysis}
                        activeLayers={activeLayers}
                    />
                </div>

                {/* Entity Popup */}
                <EntityPopup
                    entity={selectedEntity}
                    company={popupCompany}
                    onClose={handleClosePopup}
                />

                {/* Layer Toggle */}
                {!isIntelPanelOpen && (
                    <LayerToggle
                        activeLayers={activeLayers}
                        onToggle={handleLayerToggle}
                        hasIntel={geoIntelligence !== null || viewMode === 'global'}
                        viewMode={viewMode}
                    />
                )}

                {/* Attribution */}
                <div className="absolute bottom-2 left-4 z-30">
                    <p className="text-[10px] text-[var(--color-ink-muted)] opacity-50 font-mono">
                        GLOBE DATA © OPENSTREETMAP · DOSSIGRAPHICA PROJECT 2026
                    </p>
                </div>
            </div>

            {/* Bookmark Strip */}
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

            {/* Intel Panel / Global Panel */}
            {isIntelPanelOpen && !isIntelMinimized && (
                <div className="w-[480px] h-full flex flex-col dossier-panel animate-slide-open overflow-hidden">
                    {viewMode === 'company' ? (
                        <IntelPanel
                            intel={geoIntelligence}
                            loading={intelLoading}
                            error={intelError}
                            markdown={intelMarkdownContent}
                            onClose={handleToggleIntel}
                            onNavigate={handleIntelNavigate}
                        />
                    ) : (
                        <GlobalPanel
                            chainMatrix={chainMatrix}
                            riskConvergence={riskConvergence}
                            chokepointAnalysis={chokepointAnalysis}
                            loading={globalLoading}
                            error={globalError}
                            activeTab={globalTab}
                            onTabChange={handleGlobalTabChange}
                            onClose={handleToggleIntel}
                            onNavigate={handleIntelNavigate}
                        />
                    )}
                </div>
            )}
        </div>
    )
}
