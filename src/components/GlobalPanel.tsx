import { useCallback, useMemo } from 'react'
import {
    Network, ShieldAlert, Target, Loader2, ArrowRight,
    Globe, AlertTriangle, MapPin
} from 'lucide-react'
import type {
    ChainMatrix, RiskConvergence, ChokepointAnalysis
} from '../types'

type TabId = 'overview' | 'chain' | 'risks' | 'chokepoints'

interface GlobalPanelProps {
    chainMatrix: ChainMatrix | null
    riskConvergence: RiskConvergence | null
    chokepointAnalysis: ChokepointAnalysis | null
    loading: boolean
    error: string | null
    activeTab: TabId
    onTabChange: (tab: TabId) => void
    onClose: () => void
    onNavigate: (lat: number, lng: number) => void
}

const TABS: { id: TabId; label: string; icon: typeof Globe }[] = [
    { id: 'overview', label: 'Overview', icon: Globe },
    { id: 'chain', label: 'Value Chain', icon: Network },
    { id: 'risks', label: 'Macro Risks', icon: ShieldAlert },
    { id: 'chokepoints', label: 'Chokepoints', icon: Target },
]

export default function GlobalPanel({
    chainMatrix,
    riskConvergence,
    chokepointAnalysis,
    loading,
    error,
    activeTab,
    onTabChange,
    onClose,
    onNavigate
}: GlobalPanelProps) {
    const handleNavigate = useCallback((lat: number, lng: number) => {
        onNavigate(lat, lng)
    }, [onNavigate])

    if (loading) return (
        <div className="flex-1 flex flex-col items-center justify-center p-12 text-center bg-[var(--color-bg-paper)]">
            <Loader2 size={32} className="animate-spin text-[var(--color-ink)] mb-4" />
            <h2 className="text-xl font-serif italic text-[var(--color-ink)] mb-2">Synthesizing Global Data...</h2>
            <p className="text-sm font-mono text-[var(--color-ink-muted)]">SYSTEM AGGREGATION IN PROGRESS</p>
        </div>
    )

    if (error) return (
        <div className="flex-1 flex flex-col items-center justify-center p-12 text-center bg-[var(--color-bg-paper)]">
             <div className="w-16 h-16 border-2 border-[var(--color-accent-red)] flex items-center justify-center mb-6">
                  <AlertTriangle size={32} className="text-[var(--color-accent-red)]" />
             </div>
             <h2 className="text-xl font-serif font-bold text-[var(--color-ink)] mb-2">Aggregation Failed</h2>
             <p className="text-sm font-mono text-[var(--color-ink-muted)] mb-6">{error}</p>
             <button onClick={onClose} className="border border-[var(--color-ink)] px-6 py-2 font-serif font-bold hover:bg-[var(--color-ink)] hover:text-white transition-colors">
                 RETURN TO MAP
             </button>
        </div>
    )

    return (
        <div className="flex-1 flex flex-col h-full bg-[var(--color-bg-paper)]">
            {/* Dossier Header */}
            <div className="px-8 py-8 border-b-2 border-[var(--color-ink)]">
                <div className="flex items-start justify-between mb-4">
                    <div>
                        <p className="text-[10px] font-mono uppercase tracking-[0.2em] text-[var(--color-ink-muted)] mb-1">
                            Strategic Global Analysis
                        </p>
                        <h2 className="text-3xl font-serif font-bold text-[var(--color-ink)] leading-none">
                            GLOBAL VALUE CHAIN
                        </h2>
                    </div>
                    <div className="text-right">
                        <p className="text-[10px] font-mono font-bold text-[var(--color-ink)]">DOC. GVC-2026-B</p>
                        <p className="text-[10px] font-mono text-[var(--color-ink-muted)]">REV: {chainMatrix?.version || '1.0'}</p>
                    </div>
                </div>
                
                <div className="flex items-center gap-4 text-[11px] font-serif italic text-[var(--color-ink-muted)]">
                    <span>COVERAGE: 11 KEY ENTITIES</span>
                    <span>·</span>
                    <span>UPDATED: {chainMatrix?.lastUpdated || 'RECENT'}</span>
                </div>
            </div>

            {/* Index Tabs */}
            <div className="flex flex-wrap px-8 mt-4">
                {TABS.map(tab => (
                    <button
                        key={tab.id}
                        onClick={() => onTabChange(tab.id as TabId)}
                        className={`index-tab ${activeTab === tab.id ? 'active' : ''}`}
                    >
                        {tab.label}
                    </button>
                ))}
            </div>

            {/* Content Container */}
            <div className="flex-1 overflow-y-auto px-8 py-6 bg-[var(--color-bg-paper)]">
                <div className="max-w-2xl mx-auto">
                    {activeTab === 'overview' && <OverviewTab chainMatrix={chainMatrix} risk={riskConvergence} chokepoints={chokepointAnalysis} />}
                    {activeTab === 'chain' && <ChainTab matrix={chainMatrix} />}
                    {activeTab === 'risks' && <RisksTab risks={riskConvergence} onNavigate={handleNavigate} />}
                    {activeTab === 'chokepoints' && <ChokepointsTab analysis={chokepointAnalysis} onNavigate={handleNavigate} />}
                    
                    {/* Dossier Footer */}
                    <div className="mt-12 pt-6 border-t border-[var(--color-ink-muted)]/30 text-center">
                        <p className="text-[10px] font-mono text-[var(--color-ink-muted)] uppercase tracking-widest">
                            End of Global Intelligence Summary
                        </p>
                        <div className="flex justify-center gap-1 mt-2">
                             {[...Array(5)].map((_, i) => <div key={i} className="w-1 h-1 rounded-full bg-[var(--color-ink-light)]" />)}
                        </div>
                    </div>
                </div>
            </div>
        </div>
    )
}

function OverviewTab({ chainMatrix, risk, chokepoints }: { chainMatrix: ChainMatrix | null, risk: RiskConvergence | null, chokepoints: ChokepointAnalysis | null }) {
    const aggregateRisk = useMemo(() => {
        if (!risk || risk.regions.length === 0) return '0.0'
        const avg = risk.regions.reduce((sum, r) => sum + r.overallScore, 0) / risk.regions.length
        return avg.toFixed(1)
    }, [risk])

    return (
        <div className="space-y-8 animate-fade-in">
            <section>
                <h3 className="text-sm font-mono font-bold uppercase tracking-widest text-[var(--color-ink)] mb-3 border-b border-[var(--color-ink)] pb-1">Executive Summary</h3>
                <p className="text-base font-serif leading-relaxed text-[var(--color-ink-muted)] first-letter:text-4xl first-letter:font-bold first-letter:float-left first-letter:mr-2 first-letter:mt-1 first-letter:text-[var(--color-ink)]">
                    The semiconductor and AI infrastructure value chain represents the most concentrated and geopolitically sensitive network in the modern industrial era. This dossier aggregates systemic linkages, geographic risk concentrations, and critical chokepoints across the 11 dominant entities currently mapping the sector's trajectory from lithography to deployment.
                </p>
            </section>

            <div className="grid grid-cols-2 gap-px bg-[var(--color-ink)] border border-[var(--color-ink)]">
                <StatCell label="Total Dependencies" value={String(chainMatrix?.dependencies.length || 0)} />
                <StatCell label="Risk Regions" value={String(risk?.regions.length || 0)} />
                <StatCell label="Systemic Chokepoints" value={String(chokepoints?.chokepoints.length || 0)} />
                <StatCell label="Aggregate Risk Index" value={`${aggregateRisk} / 10`} />
            </div>

            <section className="bg-[var(--color-ink)] text-[var(--color-bg-paper)] p-6">
                <div className="flex items-center gap-3 mb-4">
                    <AlertTriangle size={20} className="text-[var(--color-accent-red)]" />
                    <p className="text-[10px] font-mono uppercase tracking-[0.2em] font-bold text-white">Systemic Warning</p>
                </div>
                <p className="text-sm font-serif italic leading-relaxed text-white/90">
                    High concentration in advanced manufacturing nodes (Taiwan) and specialized equipment (Netherlands) creates a "single point of failure" environment for the entire AI economy.
                </p>
            </section>
        </div>
    )
}

function ChainTab({ matrix }: { matrix: ChainMatrix | null }) {
    if (!matrix) return null
    return (
        <div className="space-y-6 animate-fade-in">
            <p className="text-[10px] font-mono uppercase tracking-widest text-[var(--color-ink-muted)] border-b border-[var(--color-ink)] pb-1">Inter-Company Dependencies</p>
            <div className="divide-y divide-[var(--color-ink)]">
                {matrix.dependencies.map((dep, i) => (
                    <div key={i} className="py-4 flex items-center justify-between group">
                        <div className="flex-1">
                            <div className="flex items-center gap-2 mb-1">
                                <span className="text-sm font-serif font-bold text-[var(--color-ink)]">{dep.from}</span>
                                <ArrowRight size={12} className="text-[var(--color-ink-muted)]" />
                                <span className="text-sm font-serif font-bold text-[var(--color-ink)]">{dep.to}</span>
                            </div>
                            <p className="text-xs font-serif italic text-[var(--color-ink-muted)]">{dep.description}</p>
                            <p className="text-[10px] font-mono text-[var(--color-ink-muted)] mt-1 uppercase opacity-60">{dep.type.replace(/_/g, ' ')}</p>
                        </div>
                        {dep.strength === 'critical' && (
                            <span className="text-[9px] font-mono font-bold text-[var(--color-accent-red)] border border-[var(--color-accent-red)] px-1.5 py-0.5">CRITICAL</span>
                        )}
                    </div>
                ))}
            </div>
        </div>
    )
}

function RisksTab({ risks, onNavigate }: { risks: RiskConvergence | null, onNavigate: (lat: number, lng: number) => void }) {
    if (!risks) return null
    return (
        <div className="space-y-6 animate-fade-in">
            <p className="text-[10px] font-mono uppercase tracking-widest text-[var(--color-ink-muted)] border-b border-[var(--color-ink)] pb-1">Geographic Risk Convergence</p>
            {risks.regions.map((risk, i) => (
                <div key={i} className="py-6 border-b border-[var(--color-border-muted)] last:border-none">
                    <div className="flex items-start justify-between mb-4">
                        <div>
                            <h4 className="text-lg font-serif font-bold text-[var(--color-ink)]">{risk.region}</h4>
                            <div className="flex flex-wrap gap-1 mt-2">
                                {risk.riskDimensions.map((dim, j) => (
                                    <span key={j} className="text-[8px] font-mono font-bold bg-[var(--color-ink-light)] text-[var(--color-ink)] px-1.5 py-0.5 uppercase">{dim}</span>
                                ))}
                            </div>
                        </div>
                        <div className="text-right">
                            <div className="text-2xl font-serif font-bold" style={{ color: getRiskColor(risk.overallScore) }}>{risk.overallScore.toFixed(1)}/10</div>
                            <p className="text-[8px] font-mono uppercase font-bold text-[var(--color-ink-muted)]">Macro Risk Index</p>
                        </div>
                    </div>
                    <p className="text-sm font-serif leading-relaxed text-[var(--color-ink-muted)] mb-4">{risk.summary}</p>
                    
                    <div className="bg-[var(--color-bg-paper-dark)] p-3 border-l-2 border-[var(--color-ink)] mb-4">
                        <p className="text-[9px] font-mono font-bold uppercase mb-2 opacity-60">Exposed Entities</p>
                        <div className="flex flex-wrap gap-2">
                            {risk.contributingCompanies.map(c => (
                                <div key={c.ticker} className="flex items-center gap-1.5">
                                    <span className="text-[10px] font-mono font-bold text-[var(--color-ink)]">{c.ticker}</span>
                                    <span className="text-[10px] font-mono text-[var(--color-ink-muted)] opacity-50">({c.riskScore}/5)</span>
                                </div>
                            ))}
                        </div>
                    </div>

                    <button 
                        onClick={() => onNavigate(risk.lat, risk.lng)}
                        className="text-[10px] font-mono font-bold border border-[var(--color-ink)] px-3 py-1 hover:bg-[var(--color-ink)] hover:text-white transition-all flex items-center gap-2"
                    >
                        INSPECT REGION <ArrowRight size={10} />
                    </button>
                </div>
            ))}
        </div>
    )
}

function ChokepointsTab({ analysis, onNavigate }: { analysis: ChokepointAnalysis | null, onNavigate: (lat: number, lng: number) => void }) {
    if (!analysis) return null
    return (
        <div className="space-y-6 animate-fade-in">
            <p className="text-[10px] font-mono uppercase tracking-widest text-[var(--color-ink-muted)] border-b border-[var(--color-ink)] pb-1">Systemic Chokepoint Registry</p>
            {analysis.chokepoints.map((cp, i) => (
                <div key={i} className="dossier-card mb-6 group border-l-4 border-[var(--color-accent-red)]">
                    <div className="flex justify-between items-start mb-2">
                        <h4 className="text-lg font-serif font-bold text-[var(--color-ink)]">{cp.name}</h4>
                        <span className={`text-[9px] font-mono font-bold px-2 py-0.5 bg-[var(--color-accent-red)] text-white`}>
                            {cp.severity.toUpperCase()}
                        </span>
                    </div>
                    <p className="text-xs font-mono text-[var(--color-ink-muted)] mb-3 flex items-center gap-1">
                        <MapPin size={10} /> {cp.location}
                    </p>
                    <p className="text-sm font-serif italic text-[var(--color-ink-muted)] leading-relaxed mb-4">
                        {cp.description}
                    </p>
                    <div className="flex flex-wrap gap-2 mb-4">
                        {cp.exposedCompanies.map(t => (
                            <span key={t} className="text-[9px] font-mono font-bold border border-[var(--color-ink-light)] px-1.5 py-0.5">{t}</span>
                        ))}
                    </div>
                    <button 
                        onClick={() => onNavigate(cp.lat, cp.lng)}
                        className="text-[10px] font-mono font-bold text-[var(--color-accent-red)] hover:underline flex items-center gap-1"
                    >
                        <MapPin size={10} /> LOCATE CHOKEPOINT
                    </button>
                </div>
            ))}
        </div>
    )
}

function StatCell({ label, value }: { label: string; value: string }) {
    return (
        <div className="bg-[var(--color-bg-paper)] p-4 flex flex-col justify-center">
            <p className="text-[9px] font-mono uppercase tracking-widest text-[var(--color-ink-muted)] mb-1 font-bold">{label}</p>
            <p className="text-xl font-serif font-bold text-[var(--color-ink)]">{value}</p>
        </div>
    )
}

function getRiskColor(score: number): string {
    if (score >= 8) return '#6a1a1a'
    if (score >= 6) return '#a33333'
    if (score >= 4) return '#a36633'
    if (score >= 2) return '#5d8a6a'
    return '#3d6a4a'
}
