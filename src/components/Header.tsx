import { ChevronDown, Brain, Loader2 } from 'lucide-react'
import { useState, useRef, useEffect } from 'react'
import { useGeoIntel } from '../useGeoIntel'
import type { Company } from '../types'

interface HeaderProps {
    companyName: string
    officeCount: number
    companies: Company[]
    hasIntel: boolean
    intelOpen: boolean
    onToggleIntel: () => void
    intelLoading?: boolean
}

export default function Header({
    companyName,
    companies,
    hasIntel,
    intelOpen,
    onToggleIntel,
    intelLoading
}: HeaderProps) {
    const [dropdownOpen, setDropdownOpen] = useState(false)
    const dropdownRef = useRef<HTMLDivElement>(null)
    const { selectedCompany, setSelectedCompany, setSelectedOfficeId, setIsIntelPanelOpen } = useGeoIntel()

    // Close dropdown on outside click
    useEffect(() => {
        function handleClickOutside(event: MouseEvent) {
            if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
                setDropdownOpen(false)
            }
        }
        document.addEventListener('mousedown', handleClickOutside)
        return () => document.removeEventListener('mousedown', handleClickOutside)
    }, [])

    return (
        <header className="z-40 bg-[var(--color-bg-paper)] border-b border-[var(--color-border-muted)] relative animate-fade-in shadow-executive">
            {/* Elegant luxury gold hairline underline at the very bottom of header */}
            <div className="absolute bottom-0 left-0 right-0 h-[2px] bg-gradient-to-r from-[var(--color-accent-gold)] via-[var(--color-bg-paper-dark)] to-[var(--color-accent-gold)] opacity-70" />

            <div className="flex items-center justify-between px-2.5 py-2.5 xs:px-3 sm:px-6 md:px-8">
                {/* Logo + Title (The Masthead) */}
                <div className="flex items-center gap-1.5 xs:gap-2 md:gap-5">
                    <svg viewBox="0 0 120 120" className="w-8 h-8 md:w-10 md:h-10" xmlns="http://www.w3.org/2000/svg">
                        <rect x="0" y="0" width="120" height="120" rx="40" ry="40" fill="#f4f3e6"/>
                        <line x1="22" y1="14" x2="22" y2="106" stroke="#1a1a1a" stroke-width="14" stroke-linecap="round" />
                        <path d="M 22 14 h 32 c 28 0 46 20 46 46 c 0 26 -18 46 -46 46 h -32" fill="none" stroke="#1a1a1a" stroke-width="14" stroke-linecap="round" />
                        <circle cx="88" cy="38" r="10" fill="#c2593f" stroke="#f4f3e6" stroke-width="3" />
                        <circle cx="94" cy="68" r="7" fill="#c5a880" stroke="#f4f3e6" stroke-width="3" />
                        <circle cx="80" cy="94" r="6" fill="#2e4d3a" stroke="#f4f3e6" stroke-width="3" />
                        <circle cx="22" cy="34" r="5" fill="#1a1a1a" stroke="#f4f3e6" stroke-width="2.5" />
                        <path d="M 88 38 Q 96 50 94 68" fill="none" stroke="#c2593f" stroke-width="1.5" stroke-dasharray="2 3" opacity="0.6"/>
                        <path d="M 94 68 Q 88 84 80 94" fill="none" stroke="#c5a880" stroke-width="1.5" stroke-dasharray="2 3" opacity="0.6"/>
                        <path d="M 22 34 Q 55 28 88 38" fill="none" stroke="#1a1a1a" stroke-width="1" stroke-dasharray="2 3" opacity="0.35"/>
                    </svg>
                    <div>
                        <h1 className="text-sm xs:text-base sm:text-lg md:text-2xl font-serif font-bold text-[var(--color-ink)] leading-none uppercase tracking-wide">
                            Dossigraphica
                        </h1>
                        <p className="text-[9px] font-mono text-[var(--color-ink-light)] uppercase tracking-[0.2em] mt-1 hidden sm:block">
                            An Atlas of Corporate Intelligence
                        </p>
                    </div>
                </div>

                {/* Company selector + Intel button */}
                <div className="flex items-center gap-1 xs:gap-1.5 md:gap-3">
                    {/* Company selector */}
                    {companies.length > 1 ? (
                        <div ref={dropdownRef} className="relative">
                            <button
                                onClick={() => setDropdownOpen(!dropdownOpen)}
                                className="flex items-center h-[34px] gap-1.5 xs:gap-2.5 px-2 xs:px-3 md:px-3.5 border border-[var(--color-border-muted)] hover:border-[var(--color-accent-gold)] hover:bg-[var(--color-bg-paper-dark)] transition-all duration-300 rounded shadow-sm cursor-pointer bg-white text-[var(--color-ink)]"
                            >
                                <span className="text-[8px] xs:text-[9px] font-mono font-bold text-[var(--color-accent-gold)] uppercase tracking-wider">Record</span>
                                <span className="inline-block text-[11px] xs:text-xs md:text-sm font-serif font-semibold max-w-[65px] xs:max-w-[90px] sm:max-w-[120px] truncate">
                                    {companyName}
                                </span>
                                <ChevronDown
                                    size={12}
                                    className={`text-[var(--color-ink-light)] transition-transform duration-300 flex-shrink-0 ${dropdownOpen ? 'rotate-180' : ''}`}
                                />
                            </button>

                            {dropdownOpen && (
                                <div className="absolute right-0 top-full mt-2 w-72 bg-[var(--color-bg-paper)] border border-[var(--color-accent-gold)] shadow-executive-lg rounded z-50 max-h-[75vh] overflow-y-auto divide-y divide-[var(--color-border-muted)] animate-fade-in">
                                    {/* Global View Option */}
                                    <button
                                        onClick={() => {
                                            setSelectedCompany(null)
                                            setSelectedOfficeId(null)
                                            setIsIntelPanelOpen(false)
                                            setDropdownOpen(false)
                                        }}
                                        className={`
                                            w-full text-left px-4 py-3
                                            transition-colors duration-200 cursor-pointer
                                            ${!selectedCompany 
                                                ? 'bg-[var(--color-bg-paper-dark)] text-[var(--color-ink)]' 
                                                : 'hover:bg-[var(--color-bg-paper-dark)] hover:text-[var(--color-ink)]'
                                            }
                                        `}
                                    >
                                        <div className="flex justify-between items-center">
                                            <div>
                                                <p className="text-xs md:text-sm font-serif font-bold text-[var(--color-ink)]">Global Value Chain</p>
                                                <p className="text-[8px] font-mono uppercase tracking-wider text-[var(--color-ink-light)] mt-0.5">
                                                    Macro Analysis · Cross-Company
                                                </p>
                                            </div>
                                            <span className="text-[8px] font-mono font-bold px-1.5 py-0.5 border border-[var(--color-accent-gold)] text-[var(--color-accent-gold)] rounded bg-white">
                                                ALL
                                            </span>
                                        </div>
                                    </button>

                                    {companies.map((company) => (
                                        <button
                                            key={company.company}
                                            onClick={() => {
                                                setSelectedCompany(company)
                                                setSelectedOfficeId(null)
                                                setIsIntelPanelOpen(false)
                                                setDropdownOpen(false)
                                            }}
                                            className={`
                                                w-full text-left px-4 py-3
                                                transition-colors duration-200 cursor-pointer
                                                ${selectedCompany?.company === company.company
                                                    ? 'bg-[var(--color-bg-paper-dark)] text-[var(--color-ink)]'
                                                    : 'hover:bg-[var(--color-bg-paper-dark)] hover:text-[var(--color-ink)]'
                                                }
                                            `}
                                        >
                                            <div className="flex justify-between items-center">
                                                <div>
                                                    <p className="text-xs md:text-sm font-serif font-bold text-[var(--color-ink)]">{company.company}</p>
                                                    <p className="text-[8px] font-mono uppercase tracking-wider text-[var(--color-ink-light)] mt-0.5">
                                                        {company.ticker} · {company.sector}
                                                    </p>
                                                </div>
                                                <span className="text-[8px] font-mono font-bold px-1.5 py-0.5 border border-[var(--color-border-muted)] text-[var(--color-ink-muted)] rounded bg-white">
                                                    {company.offices.length}
                                                </span>
                                            </div>
                                        </button>
                                    ))}
                                </div>
                            )}
                        </div>
                    ) : (
                        <div className="px-2 xs:px-3 h-[34px] border border-[var(--color-border-muted)] bg-white rounded shadow-sm flex items-center gap-1.5 xs:gap-2.5">
                            <span className="text-[8px] xs:text-[9px] font-mono font-bold text-[var(--color-accent-gold)] uppercase tracking-wider">Record</span>
                            <span className="inline-block text-[11px] xs:text-xs md:text-sm font-serif font-semibold text-[var(--color-ink)] max-w-[65px] xs:max-w-[90px] sm:max-w-[120px] truncate">{companyName}</span>
                        </div>
                    )}

                    {/* Intel toggle (The Dossier Button) */}
                    <button
                        onClick={onToggleIntel}
                        disabled={(!hasIntel && !intelLoading) || intelLoading}
                        className={`
                            flex items-center justify-center h-[34px] gap-1 md:gap-2 px-1.5 xs:px-2.5 md:px-4 border transition-all duration-300 cursor-pointer font-serif font-semibold text-xs rounded shadow-sm
                            disabled:opacity-30 disabled:cursor-not-allowed
                            ${intelOpen
                                ? 'bg-[var(--color-accent-green)] border-[var(--color-accent-green)] text-white hover:bg-[var(--color-ink-muted)] hover:border-[var(--color-ink-muted)]'
                                : 'bg-white border-[var(--color-accent-gold)] text-[var(--color-ink)] hover:bg-[var(--color-bg-paper-dark)] hover:border-[var(--color-accent-gold)]'
                            }
                        `}
                    >
                        {intelLoading ? (
                            <Loader2 size={13} className="animate-spin" />
                        ) : (
                            <Brain size={13} className={intelOpen ? 'text-white' : 'text-[var(--color-accent-gold)]'} />
                        )}
                        <span className="uppercase tracking-wider text-[9px] md:text-[10px] max-md:hidden">
                            {intelLoading ? 'Consulting...' : (!selectedCompany ? 'Global Dossier' : 'View Dossier')}
                        </span>
                    </button>
                </div>
            </div>
        </header>
    )
}

