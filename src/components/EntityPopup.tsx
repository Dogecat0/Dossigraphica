import { X, Building, ShieldAlert, Target, Factory, Users } from 'lucide-react'
import type { MapEntity, Company, Office, GeopoliticalRisk, RegionalRiskScore, Chokepoint, SupplyChainNode, CustomerNode } from '../types'

interface EntityPopupProps {
    entity: MapEntity | null
    company?: Company | null // For office context
    onClose: () => void
}

const RISK_COLORS: Record<number, string> = {
    1: '#e4dcc4', // Muted sage/gold
    2: '#c5a880', // Brushed Gold
    3: '#ad8755', // Deeper Gold/Bronze
    4: '#c2593f', // Rust Orange
    5: '#8f331d', // Deep Blood Rust
}

export default function EntityPopup({ entity, company, onClose }: EntityPopupProps) {
    if (!entity) return null

    const { type, data } = entity

    return (
        <div className="absolute top-24 right-8 w-80 max-md:fixed max-md:bottom-4 max-md:right-4 max-md:left-4 max-md:top-auto max-md:w-auto bg-[var(--color-bg-paper)] border border-[var(--color-border-muted)] border-t-4 border-t-[var(--color-accent-gold)] shadow-[var(--shadow-executive-lg)] z-50 p-6 rounded transition-all duration-300 animate-fade-in">
            <button
                onClick={onClose}
                className="absolute top-3 right-3 text-[var(--color-ink-light)] hover:text-[var(--color-accent-red)] hover:bg-[var(--color-bg-paper-dark)] p-1.5 rounded transition-all duration-200 cursor-pointer"
                aria-label="Close details"
            >
                <X size={14} />
            </button>

            {type === 'office' && <OfficeContent data={data as Office} company={company} />}
            {type === 'risk' && <RiskContent data={data as GeopoliticalRisk} />}
            {type === 'regionalRisk' && <RegionalRiskContent data={data as RegionalRiskScore} />}
            {type === 'chokepoint' && <ChokepointContent data={data as Chokepoint} />}
            {type === 'supplier' && <SupplierContent data={data as SupplyChainNode} />}
            {type === 'customer' && <CustomerContent data={data as CustomerNode} />}
        </div>
    )
}

function OfficeContent({ data, company }: { data: Office, company?: Company | null }) {
    return (
        <div className="space-y-4">
            <div className="flex items-center gap-3 border-b border-[var(--color-border-muted)] pb-3">
                <div className="bg-[var(--color-accent-gold)]/10 text-[var(--color-accent-gold)] p-2 rounded">
                    <Building size={18} />
                </div>
                <div>
                    <h3 className="text-lg font-serif font-bold leading-none text-[var(--color-ink)] mb-1">{data.city}</h3>
                    <p className="text-[10px] font-mono uppercase tracking-wider text-[var(--color-ink-light)] font-bold">
                        {data.country}
                    </p>
                </div>
            </div>

            <div className="space-y-2">
                <div className="bg-white border border-[var(--color-border-muted)] p-3 rounded shadow-executive border-l-2 border-l-[var(--color-accent-gold)]">
                    <p className="text-[9px] font-mono font-bold uppercase tracking-wider text-[var(--color-ink-light)] mb-0.5">Facility Type</p>
                    <p className="text-sm font-serif font-bold text-[var(--color-ink)] capitalize">
                        {data.type.replace(/_/g, ' ')}
                    </p>
                </div>

                {company && (
                    <div className="bg-white border border-[var(--color-border-muted)] p-3 rounded shadow-executive border-l-2 border-l-[var(--color-accent-blue)]">
                        <p className="text-[9px] font-mono font-bold uppercase tracking-wider text-[var(--color-ink-light)] mb-0.5">Operator</p>
                        <p className="text-sm font-serif font-bold text-[var(--color-ink)]">
                            {company.company} ({company.ticker})
                        </p>
                    </div>
                )}

                {data.businessFocus && (
                    <div className="bg-white border border-[var(--color-border-muted)] p-3 rounded shadow-executive border-l-2 border-l-[var(--color-accent-green)]">
                        <p className="text-[9px] font-mono font-bold uppercase tracking-wider text-[var(--color-ink-light)] mb-0.5">Key Function</p>
                        <p className="text-sm font-serif italic text-[var(--color-ink-muted)]">
                            "{data.businessFocus}"
                        </p>
                    </div>
                )}
            </div>
        </div>
    )
}

function RiskContent({ data }: { data: GeopoliticalRisk }) {
    const scoreColor = RISK_COLORS[data.riskScore] || '#c2593f'

    return (
        <div className="space-y-4">
            <div className="flex items-center gap-3 border-b border-[var(--color-border-muted)] pb-3">
                <div 
                    className="p-2 rounded"
                    style={{ backgroundColor: scoreColor + '15', color: scoreColor }}
                >
                    <ShieldAlert size={18} />
                </div>
                <div>
                    <h3 className="text-lg font-serif font-bold leading-none text-[var(--color-ink)] mb-1">{data.riskLabel}</h3>
                    <p className="text-[10px] font-mono uppercase tracking-wider text-[var(--color-ink-light)] font-bold">
                        Risk Score: {data.riskScore}/5
                    </p>
                </div>
            </div>

            <p className="text-sm font-serif italic text-[var(--color-ink-muted)] leading-relaxed bg-white border border-[var(--color-border-muted)] p-3 rounded shadow-executive">
                {data.description}
            </p>

            <div className="flex items-center justify-between">
                <span 
                    className="text-[9px] font-mono font-bold uppercase px-2.5 py-1 rounded"
                    style={{ backgroundColor: scoreColor + '15', color: scoreColor }}
                >
                    {data.impactLevel} Impact
                </span>
                <span className="text-[10px] font-mono text-[var(--color-ink-light)] bg-[var(--color-bg-paper-dark)] px-2 py-0.5 rounded">
                    Ref: {data.filingReference}
                </span>
            </div>
        </div>
    )
}

function RegionalRiskContent({ data }: { data: RegionalRiskScore }) {
    const overallScoreRounded = Math.min(5, Math.ceil(data.overallScore / 2))
    const scoreColor = RISK_COLORS[overallScoreRounded] || '#2563eb'

    return (
        <div className="space-y-4">
            <div className="flex items-center gap-3 border-b border-[var(--color-border-muted)] pb-3">
                <div 
                    className="p-2 rounded"
                    style={{ backgroundColor: scoreColor + '15', color: scoreColor }}
                >
                    <ShieldAlert size={18} />
                </div>
                <div>
                    <h3 className="text-lg font-serif font-bold leading-none text-[var(--color-ink)] mb-1">{data.region}</h3>
                    <p className="text-[10px] font-mono uppercase tracking-wider text-[var(--color-ink-light)] font-bold">
                        Macro Index: {data.overallScore.toFixed(1)}/10
                    </p>
                </div>
            </div>

            <p className="text-sm font-serif italic text-[var(--color-ink-muted)] leading-relaxed bg-white border border-[var(--color-border-muted)] p-3 rounded shadow-executive">
                {data.summary}
            </p>

            <div className="bg-white border border-[var(--color-border-muted)] p-3 rounded shadow-executive border-l-2 border-l-[var(--color-accent-gold)]">
                <p className="text-[9px] font-mono font-bold uppercase tracking-wider text-[var(--color-ink-light)] mb-2">Exposed Entities</p>
                <div className="flex flex-wrap gap-1.5">
                    {data.contributingCompanies.map((c, idx) => (
                        <span 
                            key={`${c.ticker}-${idx}`} 
                            className="text-[9px] font-mono font-bold bg-[var(--color-bg-paper-dark)] text-[var(--color-ink)] border border-[var(--color-border-muted)] px-1.5 py-0.5 rounded transition-colors hover:border-[var(--color-accent-gold)]"
                        >
                            {c.ticker}
                        </span>
                    ))}
                </div>
            </div>
        </div>
    )
}

function ChokepointContent({ data }: { data: Chokepoint }) {
    return (
        <div className="space-y-4">
            <div className="flex items-center gap-3 border-b border-[var(--color-border-muted)] pb-3">
                <div className="bg-[var(--color-accent-red)]/10 text-[var(--color-accent-red)] p-2 rounded">
                    <Target size={18} />
                </div>
                <div>
                    <h3 className="text-lg font-serif font-bold leading-none text-[var(--color-ink)] mb-1">{data.name}</h3>
                    <p className="text-[10px] font-mono uppercase tracking-wider text-[var(--color-ink-light)] font-bold">
                        {data.location}
                    </p>
                </div>
            </div>

            <p className="text-sm font-serif italic text-[var(--color-ink-muted)] leading-relaxed bg-white border border-[var(--color-border-muted)] p-3 rounded shadow-executive">
                {data.description}
            </p>

            <div className="space-y-2">
                <div className="flex items-center justify-between">
                    <span className="text-[9px] font-mono font-bold uppercase bg-[var(--color-accent-red)]/15 text-[var(--color-accent-red)] px-2.5 py-1 rounded">
                        {data.severity} Severity
                    </span>
                </div>
                <div className="bg-white border border-[var(--color-border-muted)] p-3 rounded shadow-executive border-l-2 border-l-[var(--color-accent-red)]">
                    <p className="text-[9px] font-mono font-bold uppercase tracking-wider text-[var(--color-ink-light)] mb-1">Exposed Portfolios</p>
                    <p className="text-xs font-mono text-[var(--color-ink)] font-bold leading-relaxed">
                        {data.exposedCompanies.join(', ')}
                    </p>
                </div>
            </div>
        </div>
    )
}

function SupplierContent({ data }: { data: SupplyChainNode }) {
    return (
        <div className="space-y-4">
            <div className="flex items-center gap-3 border-b border-[var(--color-border-muted)] pb-3">
                <div className="bg-[var(--color-accent-gold)]/10 text-[var(--color-accent-gold)] p-2 rounded">
                    <Factory size={18} />
                </div>
                <div>
                    <h3 className="text-lg font-serif font-bold leading-none text-[var(--color-ink)] mb-1">{data.entity}</h3>
                    <p className="text-[10px] font-mono uppercase tracking-wider text-[var(--color-ink-light)] font-bold">
                        {data.city}, {data.country}
                    </p>
                </div>
            </div>

            <div className="space-y-2">
                <div className="bg-white border border-[var(--color-border-muted)] p-3 rounded shadow-executive border-l-2 border-l-[var(--color-accent-gold)]">
                    <p className="text-[9px] font-mono font-bold uppercase tracking-wider text-[var(--color-ink-light)] mb-0.5">Role</p>
                    <p className="text-sm font-serif font-bold text-[var(--color-ink)] capitalize">
                        {data.role.replace(/_/g, ' ')}
                    </p>
                </div>

                <div className="bg-white border border-[var(--color-border-muted)] p-3 rounded shadow-executive border-l-2 border-l-[var(--color-accent-red)]">
                    <p className="text-[9px] font-mono font-bold uppercase tracking-wider text-[var(--color-ink-light)] mb-0.5">Criticality</p>
                    <p className="text-sm font-serif font-bold text-[var(--color-ink)] capitalize">
                        {data.criticality}
                    </p>
                </div>
            </div>
        </div>
    )
}

function CustomerContent({ data }: { data: CustomerNode }) {
    return (
        <div className="space-y-4">
            <div className="flex items-center gap-3 border-b border-[var(--color-border-muted)] pb-3">
                <div className="bg-[var(--color-accent-blue)]/10 text-[var(--color-accent-blue)] p-2 rounded">
                    <Users size={18} />
                </div>
                <div>
                    <h3 className="text-lg font-serif font-bold leading-none text-[var(--color-ink)] mb-1">{data.customer}</h3>
                    <p className="text-[10px] font-mono uppercase tracking-wider text-[var(--color-ink-light)] font-bold">
                        HQ: {data.hqCity}, {data.hqCountry}
                    </p>
                </div>
            </div>

            <div className="bg-white border border-[var(--color-border-muted)] p-4 rounded shadow-executive border-l-4 border-l-[var(--color-accent-blue)] flex flex-col justify-center">
                <p className="text-[9px] font-mono font-bold uppercase tracking-wider text-[var(--color-ink-light)] mb-1">Assigned Revenue Share</p>
                <p className="text-2xl font-serif font-bold text-[var(--color-ink)]">
                    {data.revenueShare}
                </p>
            </div>
        </div>
    )
}
