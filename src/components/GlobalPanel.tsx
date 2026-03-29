import { useCallback, useMemo, useState } from 'react'
import {
    Network, ShieldAlert, Target, Loader2, ArrowRight,
    Globe, AlertTriangle, MapPin, ChevronDown
} from 'lucide-react'
import type {
    ChainMatrix, RiskConvergence, ChokepointAnalysis, DependencyLink
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

/** Known tracked tickers in the system */
const TRACKED_TICKERS = new Set(['AMD', 'AMZN', 'ASML', 'AVGO', 'GOOGL', 'INTC', 'META', 'MSFT', 'MU', 'NVDA', 'TSM'])

/** Abbreviate risk dimension labels for compact display */
function abbreviateDimension(dim: string): string {
    const map: Record<string, string> = {
        trade_restriction: 'TRADE',
        regulatory_compliance: 'REG.',
        geopolitical_conflict: 'GEOP.',
        environmental_regulation: 'ENV.',
        tax_policy: 'TAX',
        labor_regulation: 'LABOR',
    }
    return map[dim] || dim.replace(/_/g, ' ').substring(0, 6).toUpperCase()
}

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

/* ================================================================
   OVERVIEW TAB (unchanged)
   ================================================================ */

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

/* ================================================================
   CHAIN TAB — Grouped by Company with Collapsible Sections
   ================================================================ */

interface DepGroup {
    ticker: string
    outgoing: DependencyLink[]  // this company depends on...
    incoming: DependencyLink[]  // ...is a customer/supplier to this company
    criticalCount: number
    totalCount: number
}

function ChainTab({ matrix }: { matrix: ChainMatrix | null }) {
    const [expandedGroups, setExpandedGroups] = useState<Set<string>>(() => new Set())

    // Group dependencies by focal company (tracked tickers only)
    const { groups, totalDeps, criticalDeps } = useMemo(() => {
        if (!matrix) return { groups: [], totalDeps: 0, criticalDeps: 0 }

        const groupMap = new Map<string, DepGroup>()
        let critical = 0

        const getOrCreate = (ticker: string): DepGroup => {
            if (!groupMap.has(ticker)) {
                groupMap.set(ticker, { ticker, outgoing: [], incoming: [], criticalCount: 0, totalCount: 0 })
            }
            return groupMap.get(ticker)!
        }

        for (const dep of matrix.dependencies) {
            if (dep.strength === 'critical') critical++

            const fromTracked = TRACKED_TICKERS.has(dep.from)
            const toTracked = TRACKED_TICKERS.has(dep.to)

            if (fromTracked) {
                const group = getOrCreate(dep.from)
                group.outgoing.push(dep)
                group.totalCount++
                if (dep.strength === 'critical') group.criticalCount++
            }

            if (toTracked) {
                const group = getOrCreate(dep.to)
                group.incoming.push(dep)
                group.totalCount++
                if (dep.strength === 'critical') group.criticalCount++
            }

            // If neither side is tracked, attribute to 'from'
            if (!fromTracked && !toTracked) {
                const group = getOrCreate(dep.from)
                group.outgoing.push(dep)
                group.totalCount++
                if (dep.strength === 'critical') group.criticalCount++
            }
        }

        // Sort: most critical first, then by total count
        const sorted = Array.from(groupMap.values()).sort((a, b) => {
            if (b.criticalCount !== a.criticalCount) return b.criticalCount - a.criticalCount
            return b.totalCount - a.totalCount
        })

        return { groups: sorted, totalDeps: matrix.dependencies.length, criticalDeps: critical }
    }, [matrix])

    // Auto-expand first group on mount
    useMemo(() => {
        if (groups.length > 0 && expandedGroups.size === 0) {
            setExpandedGroups(new Set([groups[0].ticker]))
        }
    }, [groups]) // eslint-disable-line react-hooks/exhaustive-deps

    const toggleGroup = useCallback((ticker: string) => {
        setExpandedGroups(prev => {
            const next = new Set(prev)
            if (next.has(ticker)) next.delete(ticker)
            else next.add(ticker)
            return next
        })
    }, [])

    if (!matrix) return null

    const criticalPct = totalDeps > 0 ? Math.round((criticalDeps / totalDeps) * 100) : 0

    return (
        <div className="animate-fade-in">
            <p className="text-[10px] font-mono uppercase tracking-widest text-[var(--color-ink-muted)] border-b border-[var(--color-ink)] pb-1 mb-4">
                Inter-Company Dependencies
            </p>

            {/* Summary Bar */}
            <div className="stat-summary-bar">
                <div>
                    <p className="text-[9px] font-mono uppercase tracking-widest text-[var(--color-ink-muted)] font-bold">Total Links</p>
                    <p className="text-xl font-serif font-bold text-[var(--color-ink)]">{totalDeps}</p>
                </div>
                <div>
                    <p className="text-[9px] font-mono uppercase tracking-widest text-[var(--color-ink-muted)] font-bold">Critical</p>
                    <p className="text-xl font-serif font-bold" style={{ color: '#6a1a1a' }}>{criticalDeps}</p>
                    <div className="stat-fill-bar">
                        <div className="stat-fill-bar-inner" style={{ width: `${criticalPct}%` }} />
                    </div>
                </div>
            </div>

            {/* Grouped Dependencies */}
            {groups.map(group => {
                const isExpanded = expandedGroups.has(group.ticker)

                // Sort: critical outgoing first, then outgoing, then incoming
                const sortedOutgoing = [...group.outgoing].sort((a, b) => {
                    if (a.strength === 'critical' && b.strength !== 'critical') return -1
                    if (b.strength === 'critical' && a.strength !== 'critical') return 1
                    return 0
                })

                return (
                    <div key={group.ticker} className={`dep-group ${isExpanded ? 'expanded' : ''}`}>
                        <div className="dep-group-header" onClick={() => toggleGroup(group.ticker)}>
                            <div className="flex items-center gap-3">
                                <ChevronDown size={14} className={`chevron-icon ${isExpanded ? 'rotated' : ''}`} />
                                <span className="text-sm font-serif font-bold text-[var(--color-ink)]">{group.ticker}</span>
                            </div>
                            <div className="flex items-center gap-3">
                                <span className="text-[10px] font-mono text-[var(--color-ink-muted)]">
                                    {group.totalCount} dep{group.totalCount !== 1 ? 's' : ''}
                                </span>
                                {group.criticalCount > 0 && (
                                    <span className="text-[9px] font-mono font-bold text-[var(--color-accent-red)] border border-[var(--color-accent-red)] px-1.5 py-0.5">
                                        {group.criticalCount} CRIT
                                    </span>
                                )}
                            </div>
                        </div>
                        <div className="dep-group-body">
                            {/* Outgoing: this company depends on... */}
                            {sortedOutgoing.map((dep, i) => (
                                <div key={`out-${i}`} className={`dep-row ${dep.strength === 'critical' ? 'is-critical' : ''}`}>
                                    <span className="dep-direction outgoing" title="Depends on">→</span>
                                    <div className="flex-1 min-w-0">
                                        <span className="text-xs font-serif font-bold text-[var(--color-ink)]">{dep.to}</span>
                                        <p className="text-[11px] font-serif italic text-[var(--color-ink-muted)] leading-snug mt-0.5 truncate" title={dep.description}>
                                            {dep.description.replace(/^.+depends on .+ for /, '').replace(/^.+ depends on /, '')}
                                        </p>
                                    </div>
                                    {dep.strength === 'critical' && (
                                        <span className="text-[8px] font-mono font-bold text-[var(--color-accent-red)] flex-shrink-0">CRITICAL</span>
                                    )}
                                </div>
                            ))}
                            {/* Incoming: customers of this company */}
                            {group.incoming.map((dep, i) => (
                                <div key={`in-${i}`} className={`dep-row ${dep.strength === 'critical' ? 'is-critical' : ''}`}>
                                    <span className="dep-direction incoming" title="Customer / source">◂</span>
                                    <div className="flex-1 min-w-0">
                                        <span className="text-xs font-serif font-bold text-[var(--color-ink)]">{dep.from}</span>
                                        <p className="text-[11px] font-serif italic text-[var(--color-ink-muted)] leading-snug mt-0.5 truncate" title={dep.description}>
                                            {dep.description}
                                        </p>
                                    </div>
                                    {dep.value && dep.value !== 'Undisclosed' && (
                                        <span className="text-[9px] font-mono text-[var(--color-ink-muted)] flex-shrink-0">{dep.value}</span>
                                    )}
                                </div>
                            ))}
                        </div>
                    </div>
                )
            })}
        </div>
    )
}

/* ================================================================
   RISKS TAB — Compact Sorted Table with Expandable Detail Rows
   ================================================================ */

function RisksTab({ risks, onNavigate }: { risks: RiskConvergence | null, onNavigate: (lat: number, lng: number) => void }) {
    const [expandedRegion, setExpandedRegion] = useState<string | null>(null)

    // Sort regions by overallScore descending
    const sortedRegions = useMemo(() => {
        if (!risks) return []
        return [...risks.regions].sort((a, b) => b.overallScore - a.overallScore)
    }, [risks])

    const avgRisk = useMemo(() => {
        if (sortedRegions.length === 0) return '0.0'
        const avg = sortedRegions.reduce((sum, r) => sum + r.overallScore, 0) / sortedRegions.length
        return avg.toFixed(1)
    }, [sortedRegions])

    const toggleRegion = useCallback((region: string) => {
        setExpandedRegion(prev => prev === region ? null : region)
    }, [])

    if (!risks) return null

    const highRiskCount = sortedRegions.filter(r => r.overallScore >= 8).length
    const highRiskPct = sortedRegions.length > 0 ? Math.round((highRiskCount / sortedRegions.length) * 100) : 0

    return (
        <div className="animate-fade-in">
            <p className="text-[10px] font-mono uppercase tracking-widest text-[var(--color-ink-muted)] border-b border-[var(--color-ink)] pb-1 mb-4">
                Geographic Risk Convergence
            </p>

            {/* Summary Bar */}
            <div className="stat-summary-bar">
                <div>
                    <p className="text-[9px] font-mono uppercase tracking-widest text-[var(--color-ink-muted)] font-bold">Regions</p>
                    <p className="text-xl font-serif font-bold text-[var(--color-ink)]">{sortedRegions.length}</p>
                </div>
                <div>
                    <p className="text-[9px] font-mono uppercase tracking-widest text-[var(--color-ink-muted)] font-bold">Avg Risk</p>
                    <p className="text-xl font-serif font-bold" style={{ color: getRiskColor(parseFloat(avgRisk)) }}>{avgRisk}/10</p>
                    <div className="stat-fill-bar">
                        <div className="stat-fill-bar-inner" style={{ width: `${highRiskPct}%`, background: '#2563eb' }} />
                    </div>
                </div>
            </div>

            {/* Column Headers */}
            <div className="risk-table-header">
                <span></span>
                <span>Region</span>
                <span>Score</span>
                <span>Risk Type</span>
                <span>Entities</span>
                <span></span>
            </div>

            {/* Table Rows */}
            {sortedRegions.map((risk) => {
                const isExpanded = expandedRegion === risk.region
                const dimAbbrevs = risk.riskDimensions.map(abbreviateDimension).join(', ')
                const entityCount = risk.contributingCompanies.length

                return (
                    <div key={risk.region}>
                        {/* Compact Row */}
                        <div
                            className={`risk-row ${isExpanded ? 'expanded' : ''}`}
                            onClick={() => toggleRegion(risk.region)}
                        >
                            <div className="risk-indicator" style={{ backgroundColor: getRiskColor(risk.overallScore) }} />
                            <span className="text-xs font-serif font-bold text-[var(--color-ink)] truncate">{risk.region}</span>
                            <span className="text-xs font-serif font-bold" style={{ color: getRiskColor(risk.overallScore) }}>
                                {risk.overallScore.toFixed(1)}
                            </span>
                            <span className="text-[9px] font-mono text-[var(--color-ink-muted)] truncate" title={risk.riskDimensions.join(', ')}>
                                {dimAbbrevs}
                            </span>
                            <span className="text-[10px] font-mono text-[var(--color-ink-muted)]">
                                {entityCount} co{entityCount !== 1 ? 's' : '.'}
                            </span>
                            <ChevronDown size={12} className={`chevron-icon ${isExpanded ? 'rotated' : ''}`} />
                        </div>

                        {/* Expandable Detail Panel */}
                        <div className={`risk-detail-panel ${isExpanded ? 'expanded' : ''}`}>
                            <div className="risk-detail-inner">
                                {/* Dimensions */}
                                <div className="flex flex-wrap gap-1.5 mb-3">
                                    {risk.riskDimensions.map((dim, j) => (
                                        <span key={j} className="text-[8px] font-mono font-bold bg-[var(--color-ink)] text-[var(--color-bg-paper)] px-2 py-0.5 uppercase">
                                            {dim.replace(/_/g, ' ')}
                                        </span>
                                    ))}
                                </div>

                                {/* Summary */}
                                <p className="text-sm font-serif italic leading-relaxed text-[var(--color-ink-muted)] mb-4">{risk.summary}</p>

                                {/* Entity Risk Grid — visual blocks */}
                                <div className="border-l-2 border-[var(--color-ink)] pl-3 mb-4">
                                    <p className="text-[9px] font-mono font-bold uppercase mb-2 text-[var(--color-ink-muted)]">Exposed Entities</p>
                                    <div className="risk-entity-grid">
                                        {risk.contributingCompanies.map((c, idx) => (
                                            <div key={`${c.ticker}-${idx}`} className="risk-entity-item">
                                                <span className="text-[10px] font-mono font-bold text-[var(--color-ink)] w-10">{c.ticker}</span>
                                                <div className="risk-blocks">
                                                    {[1, 2, 3, 4, 5].map(level => (
                                                        <div key={level} className={`risk-block ${level <= c.riskScore ? 'filled' : ''}`} />
                                                    ))}
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                </div>

                                {/* Navigate Button */}
                                <button
                                    onClick={(e) => { e.stopPropagation(); onNavigate(risk.lat, risk.lng) }}
                                    className="text-[10px] font-mono font-bold border border-[var(--color-ink)] px-3 py-1 hover:bg-[var(--color-ink)] hover:text-white transition-all flex items-center gap-2"
                                >
                                    INSPECT REGION <ArrowRight size={10} />
                                </button>
                            </div>
                        </div>
                    </div>
                )
            })}
        </div>
    )
}

/* ================================================================
   CHOKEPOINTS TAB (unchanged)
   ================================================================ */

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
                        {cp.exposedCompanies.map((t, idx) => (
                            <span key={`${t}-${idx}`} className="text-[9px] font-mono font-bold border border-[var(--color-ink-light)] px-1.5 py-0.5">{t}</span>
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

/* ================================================================
   SHARED COMPONENTS
   ================================================================ */

function StatCell({ label, value }: { label: string; value: string }) {
    return (
        <div className="bg-[var(--color-bg-paper)] p-4 flex flex-col justify-center">
            <p className="text-[9px] font-mono uppercase tracking-widest text-[var(--color-ink-muted)] mb-1 font-bold">{label}</p>
            <p className="text-xl font-serif font-bold text-[var(--color-ink)]">{value}</p>
        </div>
    )
}

function getRiskColor(score: number): string {
    const tier = Math.min(5, Math.ceil(score / 2))
    const colors: Record<number, string> = {
        1: '#93c5fd', // Blue-300 — minor
        2: '#3b82f6', // Blue-500 — moderate
        3: '#2563eb', // Blue-600 — elevated
        4: '#1d4ed8', // Blue-700 — high
        5: '#1e3a8a', // Blue-900 — critical
    }
    return colors[tier] || '#2563eb'
}
