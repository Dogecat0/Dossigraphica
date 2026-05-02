import { useState, useCallback, useMemo } from 'react'
import {
    Building2, DollarSign, Link2, Users, ShieldAlert,
    FileText, MapPin, AlertTriangle, Loader2, ArrowRight
} from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import rehypeRaw from 'rehype-raw'
import type {
    GeoIntelligence, SupplyChainNode,
    CustomerNode, GeopoliticalRisk
} from '../types'
import AnimatedNumber from './AnimatedNumber'

type TabId = 'overview' | 'revenue' | 'supply' | 'customers' | 'risks' | 'research'

interface IntelPanelProps {
    intel: GeoIntelligence | null
    loading?: boolean
    error?: string | null
    markdown?: string | null
    onClose: () => void
    onNavigate: (lat: number, lng: number) => void
}

const TABS: { id: TabId; label: string; icon: typeof Building2 }[] = [
    { id: 'overview', label: 'Overview', icon: Building2 },
    { id: 'revenue', label: 'Revenue', icon: DollarSign },
    { id: 'supply', label: 'Supply Chain', icon: Link2 },
    { id: 'customers', label: 'Customers', icon: Users },
    { id: 'risks', label: 'Risks', icon: ShieldAlert },
    { id: 'research', label: 'Research', icon: FileText },
]

const RISK_COLORS: Record<number, string> = {
    1: '#3d6a4a',
    2: '#5d8a6a',
    3: '#b08d57',
    4: '#a36633',
    5: '#a33333',
}

function formatRevenue(value: number | null): string {
    if (value === null) return 'N/A'
    if (value >= 1e9) return `$${(value / 1e9).toFixed(1)}B`
    if (value >= 1e6) return `$${(value / 1e6).toFixed(0)}M`
    return `$${value.toLocaleString()}`
}

export default function IntelPanel({ intel, loading, error, markdown, onClose, onNavigate }: IntelPanelProps) {
    const [activeTab, setActiveTab] = useState<TabId>('overview')

    const handleNavigate = useCallback((lat: number, lng: number) => {
        onNavigate(lat, lng)
    }, [onNavigate])

    const availableTabs = useMemo(() => {
        let tabs = [...TABS]
        if (!markdown) {
            tabs = tabs.filter(t => t.id !== 'research')
        }
        return tabs
    }, [markdown])

    if (loading) return (
        <div className="flex-1 flex flex-col items-center justify-center p-12 text-center bg-[var(--color-bg-paper)]">
            <Loader2 size={32} className="animate-spin text-[var(--color-ink)] mb-4" />
            <h2 className="text-xl font-serif italic text-[var(--color-ink)] mb-2">Consulting the Archives...</h2>
            <p className="text-sm font-mono text-[var(--color-ink-muted)]">PLEASE STAND BY</p>
        </div>
    )

    if (error) return (
        <div className="flex-1 flex flex-col items-center justify-center p-12 text-center bg-[var(--color-bg-paper)]">
            <div className="w-16 h-16 border-2 border-[var(--color-accent-red)] flex items-center justify-center mb-6">
                <AlertTriangle size={32} className="text-[var(--color-accent-red)]" />
            </div>
            <h2 className="text-xl font-serif font-bold text-[var(--color-ink)] mb-2">Record Not Found</h2>
            <p className="text-sm font-mono text-[var(--color-ink-muted)] mb-6">{error}</p>
            <button onClick={onClose} className="border border-[var(--color-ink)] px-6 py-2 font-serif font-bold hover:bg-[var(--color-ink)] hover:text-white transition-colors">
                RETURN TO MAP
            </button>
        </div>
    )

    if (!intel) return null

    return (
        <div className="flex-1 flex flex-col h-full bg-[var(--color-bg-paper)]">
            {/* Dossier Header */}
            <div className="px-8 py-8 border-b-2 border-[var(--color-ink)]">
                <div className="flex items-start justify-between mb-4">
                    <div>
                        <p className="text-[10px] font-mono uppercase tracking-[0.2em] text-[var(--color-ink-muted)] mb-1">
                            Corporate Intelligence Dossier
                        </p>
                        <h2 className="text-3xl font-serif font-bold text-[var(--color-ink)] leading-none">
                            {intel.company}
                        </h2>
                    </div>
                    <div className="text-right">
                        <p className="text-[10px] font-mono font-bold text-[var(--color-ink)]">NO. {intel.ticker}-2026</p>
                        <p className="text-[10px] font-mono text-[var(--color-ink-muted)]">SEC {intel.anchorFiling.type} · {intel.anchorFiling.fiscalPeriod}</p>
                    </div>
                </div>

                <div className="flex items-center gap-4 text-[11px] font-serif italic text-[var(--color-ink-muted)]">
                    <span>STATUS: ACTIVE / VERIFIED</span>
                </div>
            </div>

            {/* Index Tabs (Flat Multi-row) */}
            <div className="flex flex-wrap px-8 mt-4">
                {availableTabs.map(tab => (
                    <button
                        key={tab.id}
                        onClick={() => setActiveTab(tab.id as TabId)}
                        className={`index-tab ${activeTab === tab.id ? 'active' : ''}`}
                    >
                        {tab.label}
                    </button>
                ))}
            </div>

            {/* Content Container (Paper style) */}
            <div className="flex-1 overflow-y-auto px-8 py-6 bg-[var(--color-bg-paper)]">
                <div className="max-w-2xl mx-auto">
                    {activeTab === 'overview' && <OverviewTab intel={intel} />}
                    {activeTab === 'revenue' && <RevenueTab geo={intel.revenueGeography} />}
                    {activeTab === 'supply' && <SupplyChainTab nodes={intel.supplyChain} onNavigate={handleNavigate} />}
                    {activeTab === 'customers' && <CustomersTab customers={intel.customerConcentration} onNavigate={handleNavigate} />}
                    {activeTab === 'risks' && <RisksTab risks={intel.geopoliticalRisks} onNavigate={handleNavigate} />}
                    {activeTab === 'research' && markdown && <ResearchTab markdown={markdown} onNavigate={handleNavigate} />}

                    {/* Dossier Footer */}
                    <div className="mt-12 pt-6 border-t border-[var(--color-ink-muted)]/30 text-center">
                        <p className="text-[10px] font-mono text-[var(--color-ink-muted)] uppercase tracking-widest">
                            End of Document · Printed {intel.generatedDate}
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

/* ===== Tab Components ===== */

function OverviewTab({ intel }: { intel: GeoIntelligence }) {
    const countries = new Set(intel.offices.map(o => o.country))
    return (
        <div className="space-y-8 animate-fade-in">
            <section>
                <h3 className="text-sm font-mono font-bold uppercase tracking-widest text-[var(--color-ink)] mb-3 border-b border-[var(--color-ink)] pb-1">Executive Summary</h3>
                <p className="text-base font-serif leading-relaxed text-[var(--color-ink-muted)] first-letter:text-4xl first-letter:font-bold first-letter:float-left first-letter:mr-2 first-letter:mt-1 first-letter:text-[var(--color-ink)]">
                    {intel.description}
                </p>
            </section>

            <div className="grid grid-cols-2 gap-px bg-[var(--color-ink)] border border-[var(--color-ink)]">
                <StatCell label="Total Locations" value={String(intel.offices.length)} />
                <StatCell label="Global Jurisdictions" value={String(countries.size)} />
                <StatCell label="Supply Chain Nodes" value={String(intel.supplyChain.length)} />
                <StatCell label="Risk Indicators" value={String(intel.geopoliticalRisks.length)} />
            </div>

            <section className="bg-[var(--color-ink)] text-[var(--color-bg-paper)] p-6">
                <p className="text-[10px] font-mono uppercase tracking-[0.2em] mb-2 opacity-70 text-white">Annual Financial Performance</p>
                <div className="flex items-baseline justify-between">
                    <h4 className="text-3xl font-serif font-bold">
                        <AnimatedNumber value={intel.revenueGeography.totalRevenue} formatter={formatRevenue} />
                    </h4>
                    <span className="text-[10px] font-mono font-bold border border-white/30 px-2 py-0.5">CURRENCY: {intel.revenueGeography.currency}</span>
                </div>
            </section>

            {intel.revenueGeography.concentrationRisk && (
                <section className="border-2 border-[var(--color-accent-red)] p-4 relative">
                    <div className="absolute top-0 right-4 -translate-y-1/2 bg-[var(--color-bg-paper)] px-2">
                        <AlertTriangle size={16} className="text-[var(--color-accent-red)]" />
                    </div>
                    <p className="text-[10px] font-mono font-bold text-[var(--color-accent-red)] uppercase mb-2">Strategic Advisory / Warning</p>
                    <p className="text-sm font-serif italic font-semibold leading-relaxed text-[var(--color-ink)]">
                        {intel.revenueGeography.concentrationRisk}
                    </p>
                </section>
            )}
        </div>
    )
}

function RevenueTab({ geo }: { geo: GeoIntelligence['revenueGeography'] }) {
    return (
        <div className="space-y-8 animate-fade-in">
            <section className="border-b-2 border-[var(--color-ink)] pb-4">
                <p className="text-[10px] font-mono uppercase tracking-widest text-[var(--color-ink-muted)] mb-2">Consolidated Revenue Report — FY{geo.fiscalYear}</p>
                <div className="flex justify-between items-end">
                    <h3 className="text-4xl font-serif font-bold"><AnimatedNumber value={geo.totalRevenue} formatter={formatRevenue} /></h3>
                    <p className="text-xs font-mono text-[var(--color-ink-muted)]">DATA SOURCE: {geo.source}</p>
                </div>
            </section>

            <table className="w-full font-serif border-collapse">
                <thead>
                    <tr className="border-b border-[var(--color-ink)] text-left">
                        <th className="py-2 text-[10px] font-mono uppercase font-bold pr-4">Regional Segment</th>
                        <th className="py-2 text-[10px] font-mono uppercase font-bold text-right pr-4">Revenue</th>
                        <th className="py-2 text-[10px] font-mono uppercase font-bold text-right">Share</th>
                    </tr>
                </thead>
                <tbody className="divide-y divide-[var(--color-border-muted)]">
                    {geo.segments.map((seg, i) => (
                        <tr key={i} className="group hover:bg-[var(--color-bg-paper-dark)] transition-colors">
                            <td className="py-4 font-bold text-[var(--color-ink)]">{seg.region}</td>
                            <td className="py-4 text-right font-mono pr-4"><AnimatedNumber value={seg.revenue} formatter={formatRevenue} /></td>
                            <td className="py-4 text-right font-mono font-bold text-[var(--color-accent-blue)]"><AnimatedNumber value={seg.percentage} formatter={(val) => `${((val || 0) * 100).toFixed(1)}%`} /></td>
                        </tr>
                    ))}
                </tbody>
            </table>

            {geo.concentrationRisk && (
                <div className="p-6 bg-[var(--color-bg-paper-dark)] border-l-4 border-[var(--color-accent-red)]">
                    <p className="text-[10px] font-mono font-bold text-[var(--color-accent-red)] uppercase mb-2">Concentration Risk Analysis</p>
                    <p className="text-sm font-serif leading-relaxed italic">{geo.concentrationRisk}</p>
                </div>
            )}
        </div>
    )
}

function SupplyChainTab({ nodes, onNavigate }: { nodes: SupplyChainNode[]; onNavigate: (lat: number, lng: number) => void }) {
    return (
        <div className="space-y-6 animate-fade-in">
            <p className="text-[10px] font-mono uppercase tracking-widest text-[var(--color-ink-muted)] border-b border-[var(--color-ink)] pb-1">Supply Chain Infrastructure</p>
            <div className="divide-y divide-[var(--color-ink)]">
                {nodes.map((node, i) => (
                    <div key={i} className="py-6 flex gap-4 group">
                        <div className="flex-1">
                            <div className="flex items-start justify-between mb-2">
                                <h4 className="text-lg font-serif font-bold text-[var(--color-ink)]">{node.entity}</h4>
                                <span className={`text-[9px] font-mono font-bold px-2 py-0.5 border ${node.criticality === 'critical' ? 'border-[var(--color-accent-red)] text-[var(--color-accent-red)]' : 'border-[var(--color-ink)]'}`}>
                                    {node.criticality.toUpperCase()}
                                </span>
                            </div>
                            <p className="text-xs font-mono text-[var(--color-ink-muted)] mb-3 flex items-center gap-1">
                                <MapPin size={10} /> {node.city}, {node.country}
                            </p>
                            <p className="text-sm font-serif italic text-[var(--color-ink-muted)] leading-snug mb-4">
                                Strategic Role: <span className="text-[var(--color-ink)] font-bold">{node.role.replace(/_/g, ' ')}</span>
                                <br />Produces: {node.product}
                            </p>
                            <button
                                onClick={() => node.lat && node.lng && onNavigate(node.lat, node.lng)}
                                className={`text-[10px] font-mono font-bold border border-[var(--color-ink)] px-3 py-1 transition-all flex items-center gap-2 ${node.lat && node.lng ? 'hover:bg-[var(--color-ink)] hover:text-white cursor-pointer' : 'opacity-50 cursor-not-allowed'}`}
                                disabled={!node.lat || !node.lng}
                            >
                                COORDINATES: {node.lat != null ? node.lat.toFixed(4) : 'N/A'}, {node.lng != null ? node.lng.toFixed(4) : 'N/A'} <ArrowRight size={10} />
                            </button>
                        </div>
                    </div>
                ))}
            </div>
        </div>
    )
}

function CustomersTab({ customers, onNavigate }: { customers: CustomerNode[]; onNavigate: (lat: number, lng: number) => void }) {
    return (
        <div className="space-y-6 animate-fade-in">
            <p className="text-[10px] font-mono uppercase tracking-widest text-[var(--color-ink-muted)] border-b border-[var(--color-ink)] pb-1">Key Customer Relationships</p>
            {customers.map((cust, i) => (
                <div key={i} className="dossier-card mb-4 group hover:bg-[var(--color-bg-paper-dark)] transition-colors">
                    <div className="flex justify-between items-start mb-2">
                        <h4 className="text-lg font-serif font-bold text-[var(--color-ink)]">{cust.customer}</h4>
                        <span className="text-[10px] font-mono font-bold bg-[var(--color-ink)] text-white px-2 py-0.5">{cust.revenueShare}</span>
                    </div>
                    <p className="text-xs font-serif italic text-[var(--color-ink-muted)] mb-3">{cust.relationship}</p>
                    <button
                        onClick={() => cust.lat && cust.lng && onNavigate(cust.lat, cust.lng)}
                        className={`text-[10px] font-mono font-bold text-[var(--color-accent-blue)] flex items-center gap-1 ${cust.lat && cust.lng ? 'hover:underline cursor-pointer' : 'opacity-50 cursor-not-allowed'}`}
                        disabled={!cust.lat || !cust.lng}
                    >
                        <MapPin size={10} /> {cust.hqCity}, {cust.hqCountry}
                    </button>
                </div>
            ))}
        </div>
    )
}

function RisksTab({ risks, onNavigate }: { risks: GeopoliticalRisk[]; onNavigate: (lat: number, lng: number) => void }) {
    const sorted = [...risks].sort((a, b) => b.riskScore - a.riskScore)
    return (
        <div className="space-y-6 animate-fade-in">
            <p className="text-[10px] font-mono uppercase tracking-widest text-[var(--color-ink-muted)] border-b border-[var(--color-ink)] pb-1">Geopolitical Intelligence Report</p>
            {sorted.map((risk, i) => (
                <div key={i} className="py-6 border-b border-[var(--color-border-muted)] last:border-none">
                    <div className="flex items-start justify-between mb-3">
                        <div className="flex-1">
                            <h4 className="text-lg font-serif font-bold text-[var(--color-ink)] flex items-center gap-2">
                                <span className="w-2 h-2 rounded-full" style={{ background: RISK_COLORS[risk.riskScore] }} />
                                {risk.riskLabel}
                            </h4>
                            <p className="text-[10px] font-mono text-[var(--color-ink-muted)] mt-1">{risk.region} · UPDATED {risk.lastUpdated}</p>
                        </div>
                        <div className="text-right">
                            <p className="text-2xl font-serif font-bold" style={{ color: RISK_COLORS[risk.riskScore] }}>{risk.riskScore}/5</p>
                            <p className="text-[8px] font-mono uppercase font-bold text-[var(--color-ink-muted)]">Risk Index</p>
                        </div>
                    </div>
                    <p className="text-sm font-serif leading-relaxed text-[var(--color-ink-muted)] mb-4">{risk.description}</p>
                    <div className="flex items-center gap-3">
                        <span className="text-[10px] font-mono font-bold border border-[var(--color-ink)] px-2 py-0.5 uppercase">{risk.riskCategory.replace(/_/g, ' ')}</span>
                        <button
                            onClick={() => risk.lat && risk.lng && onNavigate(risk.lat, risk.lng)}
                            className={`text-[10px] font-mono font-bold text-[var(--color-ink)] flex items-center gap-1 ${risk.lat && risk.lng ? 'hover:underline cursor-pointer' : 'opacity-50 cursor-not-allowed'}`}
                            disabled={!risk.lat || !risk.lng}
                        >
                            <MapPin size={10} /> VIEW REGION
                        </button>
                    </div>
                </div>
            ))}
        </div>
    )
}

function ResearchTab({ markdown, onNavigate }: { markdown: string; onNavigate: (lat: number, lng: number) => void }) {
    return (
        <div className="animate-fade-in research-prose-archivist font-serif">
            <ReactMarkdown
                rehypePlugins={[rehypeRaw]}
                components={{
                    h1: ({ children }) => <h1 className="text-3xl font-serif font-bold text-[var(--color-ink)] mt-10 mb-6 border-b-2 border-[var(--color-ink)] pb-2">{children}</h1>,
                    h2: ({ children }) => <h2 className="text-xl font-serif font-bold text-[var(--color-ink)] mt-8 mb-4 border-b border-[var(--color-ink)] pb-1">{children}</h2>,
                    h3: ({ children }) => <h3 className="text-lg font-serif italic font-bold text-[var(--color-ink)] mt-6 mb-3">{children}</h3>,
                    p: ({ children }) => <p className="text-base leading-relaxed text-[var(--color-ink-muted)] mb-5">{children}</p>,
                    ul: ({ children }) => <ul className="list-disc pl-5 mb-5 text-base text-[var(--color-ink-muted)] space-y-2">{children}</ul>,
                    ol: ({ children }) => <ol className="list-decimal pl-5 mb-5 text-base text-[var(--color-ink-muted)] space-y-2">{children}</ol>,
                    li: ({ children }) => <li>{children}</li>,
                    a: ({ children, href }) => {
                        if (href && href.startsWith('geo:')) {
                            const [lat, lng] = href.replace('geo:', '').split(',').map(Number)
                            return (
                                <button
                                    onClick={(e) => {
                                        e.preventDefault()
                                        if (!isNaN(lat) && !isNaN(lng)) onNavigate(lat, lng)
                                    }}
                                    className="inline-flex items-center gap-1 text-[var(--color-accent-blue)] font-bold hover:underline transition-colors"
                                    title="View on Map"
                                >
                                    <MapPin size={12} className="inline" />
                                    {children}
                                </button>
                            )
                        }
                        return <a href={href} target="_blank" rel="noopener noreferrer" className="text-[var(--color-accent-blue)] font-bold hover:underline">{children}</a>
                    },
                    strong: ({ children }) => <strong className="font-bold text-[var(--color-ink)]">{children}</strong>,
                    blockquote: ({ children }) => <blockquote className="border-l-4 border-[var(--color-ink)] pl-6 italic text-[var(--color-ink-muted)] my-8 py-2 bg-[var(--color-bg-paper-dark)]">{children}</blockquote>,
                }}
            >
                {markdown}
            </ReactMarkdown>
        </div>
    )
}

/* ===== Small Reusable Components ===== */

function StatCell({ label, value }: { label: string; value: string }) {
    return (
        <div className="bg-[var(--color-bg-paper)] p-4 flex flex-col justify-center">
            <p className="text-[9px] font-mono uppercase tracking-widest text-[var(--color-ink-muted)] mb-1 font-bold">{label}</p>
            <p className="text-xl font-serif font-bold text-[var(--color-ink)]">{value}</p>
        </div>
    )
}
