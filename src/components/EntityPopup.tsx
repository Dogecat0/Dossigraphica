import { X, Building, ShieldAlert, Target, Factory, Users } from 'lucide-react'
import type { MapEntity, Company, Office, GeopoliticalRisk, RegionalRiskScore, Chokepoint, SupplyChainNode, CustomerNode } from '../types'

interface EntityPopupProps {
    entity: MapEntity | null
    company?: Company | null // For office context
    onClose: () => void
}

export default function EntityPopup({ entity, company, onClose }: EntityPopupProps) {
    if (!entity) return null

    const { type, data } = entity

    return (
        <div className="absolute top-24 right-8 w-80 bg-[var(--color-bg-paper)] border-2 border-[var(--color-ink)] shadow-[8px_8px_0_var(--color-ink)] z-50 p-6 animate-fade-in">
            <button
                onClick={onClose}
                className="absolute top-2 right-2 text-[var(--color-ink)] hover:bg-[var(--color-ink)] hover:text-white p-1 transition-colors"
            >
                <X size={16} />
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
        <>
            <div className="flex items-start gap-3 mb-4">
                <div className="bg-[var(--color-ink)] text-white p-2">
                    <Building size={20} />
                </div>
                <div>
                    <h3 className="text-lg font-serif font-bold leading-none mb-1">{data.city}</h3>
                    <p className="text-xs font-mono uppercase tracking-wider text-[var(--color-ink-muted)]">
                        {data.country}
                    </p>
                </div>
            </div>

            <div className="space-y-3">
                <div className="border-l-2 border-[var(--color-ink-light)] pl-3">
                    <p className="text-[10px] font-mono font-bold uppercase text-[var(--color-ink-muted)]">Facility Type</p>
                    <p className="text-sm font-serif font-bold text-[var(--color-ink)] capitalize">
                        {data.type.replace(/_/g, ' ')}
                    </p>
                </div>

                {company && (
                    <div className="border-l-2 border-[var(--color-ink-light)] pl-3">
                        <p className="text-[10px] font-mono font-bold uppercase text-[var(--color-ink-muted)]">Operator</p>
                        <p className="text-sm font-serif font-bold text-[var(--color-ink)]">
                            {company.company}
                        </p>
                    </div>
                )}

                {data.businessFocus && (
                    <div className="border-l-2 border-[var(--color-ink-light)] pl-3">
                        <p className="text-[10px] font-mono font-bold uppercase text-[var(--color-ink-muted)]">Key Function</p>
                        <p className="text-sm font-serif italic text-[var(--color-ink)]">
                            "{data.businessFocus}"
                        </p>
                    </div>
                )}
            </div>
        </>
    )
}

function RiskContent({ data }: { data: GeopoliticalRisk }) {
    return (
        <>
            <div className="flex items-start gap-3 mb-4">
                <div className="bg-[var(--color-accent-red)] text-white p-2">
                    <ShieldAlert size={20} />
                </div>
                <div>
                    <h3 className="text-lg font-serif font-bold leading-none mb-1">{data.riskLabel}</h3>
                    <p className="text-xs font-mono uppercase tracking-wider text-[var(--color-ink-muted)]">
                        Risk Score: {data.riskScore}/5
                    </p>
                </div>
            </div>
            <p className="text-sm font-serif italic text-[var(--color-ink)] mb-4 leading-relaxed">
                {data.description}
            </p>
            <div className="flex items-center gap-2">
                <span className="text-[9px] font-mono font-bold uppercase bg-[var(--color-ink)] text-white px-2 py-1">
                    {data.impactLevel} Impact
                </span>
                <span className="text-[9px] font-mono uppercase text-[var(--color-ink-muted)]">
                    Ref: {data.filingReference}
                </span>
            </div>
        </>
    )
}

function RegionalRiskContent({ data }: { data: RegionalRiskScore }) {
    return (
        <>
             <div className="flex items-start gap-3 mb-4">
                <div className="bg-[#6a1a1a] text-white p-2">
                    <ShieldAlert size={20} />
                </div>
                <div>
                    <h3 className="text-lg font-serif font-bold leading-none mb-1">{data.region}</h3>
                    <p className="text-xs font-mono uppercase tracking-wider text-[var(--color-ink-muted)]">
                        Macro Risk Index: {data.overallScore.toFixed(1)}/10
                    </p>
                </div>
            </div>
            <p className="text-sm font-serif italic text-[var(--color-ink)] mb-4 leading-relaxed">
                {data.summary}
            </p>
            <div className="bg-[var(--color-bg-paper-dark)] p-3 border-l-2 border-[var(--color-ink)]">
                <p className="text-[9px] font-mono font-bold uppercase mb-2 opacity-60">Exposed Entities</p>
                <div className="flex flex-wrap gap-1">
                    {data.contributingCompanies.map(c => (
                        <span key={c.ticker} className="text-[10px] font-mono font-bold border border-[var(--color-ink-light)] px-1">{c.ticker}</span>
                    ))}
                </div>
            </div>
        </>
    )
}

function ChokepointContent({ data }: { data: Chokepoint }) {
    return (
        <>
            <div className="flex items-start gap-3 mb-4">
                <div className="bg-[var(--color-accent-red)] text-white p-2">
                    <Target size={20} />
                </div>
                <div>
                    <h3 className="text-lg font-serif font-bold leading-none mb-1">{data.name}</h3>
                    <p className="text-xs font-mono uppercase tracking-wider text-[var(--color-ink-muted)]">
                        {data.location}
                    </p>
                </div>
            </div>
            <p className="text-sm font-serif italic text-[var(--color-ink)] mb-4 leading-relaxed">
                {data.description}
            </p>
             <div className="flex items-center gap-2 mb-2">
                <span className="text-[9px] font-mono font-bold uppercase bg-[var(--color-accent-red)] text-white px-2 py-1">
                    {data.severity} Severity
                </span>
            </div>
            <div className="text-[10px] font-mono text-[var(--color-ink-muted)]">
                Exposed: {data.exposedCompanies.join(', ')}
            </div>
        </>
    )
}

function SupplierContent({ data }: { data: SupplyChainNode }) {
    return (
        <>
             <div className="flex items-start gap-3 mb-4">
                <div className="bg-[var(--color-ink)] text-white p-2">
                    <Factory size={20} />
                </div>
                <div>
                    <h3 className="text-lg font-serif font-bold leading-none mb-1">{data.entity}</h3>
                    <p className="text-xs font-mono uppercase tracking-wider text-[var(--color-ink-muted)]">
                        {data.city}, {data.country}
                    </p>
                </div>
            </div>
            <div className="space-y-2">
                 <div className="border-l-2 border-[var(--color-ink-light)] pl-3">
                    <p className="text-[10px] font-mono font-bold uppercase text-[var(--color-ink-muted)]">Role</p>
                    <p className="text-sm font-serif font-bold text-[var(--color-ink)] capitalize">{data.role.replace(/_/g, ' ')}</p>
                 </div>
                 <div className="border-l-2 border-[var(--color-ink-light)] pl-3">
                    <p className="text-[10px] font-mono font-bold uppercase text-[var(--color-ink-muted)]">Criticality</p>
                    <p className="text-sm font-serif font-bold text-[var(--color-ink)] capitalize">{data.criticality}</p>
                 </div>
            </div>
        </>
    )
}

function CustomerContent({ data }: { data: CustomerNode }) {
    return (
        <>
             <div className="flex items-start gap-3 mb-4">
                <div className="bg-[#06b6d4] text-white p-2">
                    <Users size={20} />
                </div>
                <div>
                    <h3 className="text-lg font-serif font-bold leading-none mb-1">{data.customer}</h3>
                    <p className="text-xs font-mono uppercase tracking-wider text-[var(--color-ink-muted)]">
                        {data.hqCity}, {data.hqCountry}
                    </p>
                </div>
            </div>
             <div className="border-l-2 border-[var(--color-ink-light)] pl-3">
                <p className="text-[10px] font-mono font-bold uppercase text-[var(--color-ink-muted)]">Revenue Share</p>
                <p className="text-xl font-serif font-bold text-[var(--color-ink)]">{data.revenueShare}</p>
             </div>
        </>
    )
}
