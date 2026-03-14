import { ExternalLink, MapPin, Users, Building2, Calendar, X } from 'lucide-react'
import type { Office, Company, OfficeType } from '../types'
import type { LucideIcon } from 'lucide-react'

const TYPE_CONFIG: Record<OfficeType, { label: string; color: string; bg: string }> = {
    headquarters: { label: 'Headquarters', color: '#1a1a1a', bg: '#f4f3e6' },
    regional: { label: 'Regional Office', color: '#4a4a4a', bg: '#f4f3e6' },
    engineering: { label: 'Engineering Center', color: '#4a4a4a', bg: '#f4f3e6' },
    satellite: { label: 'Satellite Office', color: '#8a8a8a', bg: '#f4f3e6' },
    manufacturing: { label: 'Manufacturing Facility', color: '#a36633', bg: '#fdfcf0' },
    data_center: { label: 'Data Center', color: '#2a5a8a', bg: '#fdfcf0' },
    sales: { label: 'Sales Office', color: '#3d6a4a', bg: '#fdfcf0' },
    logistics: { label: 'Logistics Hub', color: '#a33333', bg: '#fdfcf0' },
}

interface OfficePopupProps {
    office: Office | null
    company: Company | null
    onClose: () => void
}

export default function OfficePopup({ office, company, onClose }: OfficePopupProps) {
    if (!office || !company) return null

    const typeConfig = TYPE_CONFIG[office.type] || TYPE_CONFIG.satellite

    return (
        <div className="animate-popup-enter bg-[var(--color-bg-paper)] border-2 border-[var(--color-ink)] absolute bottom-10 left-12 z-50 w-[360px] max-w-[calc(100vw-48px)] shadow-[6px_6px_0_var(--color-ink)]">
            <div className="relative">
                {/* Header Strip */}
                <div className="bg-[var(--color-ink)] px-5 py-2 flex justify-between items-center">
                    <span className="text-[10px] font-mono font-bold text-white uppercase tracking-widest">
                        Location Record NO. {office.id.slice(0, 8).toUpperCase()}
                    </span>
                    <button
                        onClick={onClose}
                        className="text-white hover:text-[var(--color-bg-paper)] transition-colors cursor-pointer"
                        aria-label="Close record"
                    >
                        <X size={14} />
                    </button>
                </div>

                <div className="p-6">
                    <div className="flex items-center gap-3 mb-4">
                        <span
                            className="inline-block px-2 py-0.5 border border-[var(--color-ink)] text-[9px] font-mono font-bold uppercase tracking-tight"
                            style={{ color: typeConfig.color, background: 'white' }}
                        >
                            {typeConfig.label}
                        </span>
                        <div className="h-px flex-1 bg-[var(--color-ink)] opacity-20" />
                    </div>

                    <h3 className="text-2xl font-serif font-bold text-[var(--color-ink)] leading-tight mb-1">
                        {office.name}
                    </h3>
                    <p className="text-sm font-serif italic text-[var(--color-ink-muted)] border-b border-[var(--color-ink)] pb-4 mb-4">
                        A subsidiary branch of {company.company}
                    </p>

                    <div className="space-y-4">
                        {office.address && <DetailRow icon={MapPin} label="Physical Address" value={office.address} />}
                        {office.businessFocus && <DetailRow icon={Building2} label="Operational Focus" value={office.businessFocus} />}
                        {office.size && <DetailRow icon={Users} label="Personnel Estimate" value={office.size} />}
                        {office.established && <DetailRow icon={Calendar} label="Date Established" value={office.established} />}
                    </div>

                    <div className="mt-8">
                        <a
                            href={company.website}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="flex items-center justify-center gap-2 w-full py-2.5 border-2 border-[var(--color-ink)] text-sm font-serif font-bold text-[var(--color-ink)] hover:bg-[var(--color-ink)] hover:text-white transition-all no-underline"
                        >
                            <ExternalLink size={14} />
                            Visit {company.company} Digital Portal
                        </a>
                    </div>
                </div>

                {/* Footer Coordinates */}
                <div className="px-6 py-3 border-t border-[var(--color-ink)] bg-[var(--color-bg-paper-dark)] flex justify-between items-center text-[10px] font-mono font-bold text-[var(--color-ink-muted)]">
                    <span>LAT: {office.lat.toFixed(6)}</span>
                    <span className="opacity-30">|</span>
                    <span>LNG: {office.lng.toFixed(6)}</span>
                </div>
            </div>
        </div>
    )
}

interface DetailRowProps {
    icon: LucideIcon
    label: string
    value: string
}

function DetailRow({ icon: Icon, label, value }: DetailRowProps) {
    return (
        <div className="flex items-start gap-4">
            <Icon size={16} className="text-[var(--color-ink)] mt-1 flex-shrink-0" />
            <div className="min-w-0">
                <p className="text-[9px] font-mono font-bold uppercase tracking-widest text-[var(--color-ink-muted)] mb-0.5">
                    {label}
                </p>
                <p className="text-sm font-serif text-[var(--color-ink)] leading-snug">{value}</p>
            </div>
        </div>
    )
}
