import { ChevronDown, Brain, Loader2, BookOpen } from 'lucide-react'
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

            <div className="flex items-center justify-between px-6 py-3.5 md:px-8">
                {/* Logo + Title (The Masthead) */}
                <div className="flex items-center gap-4 md:gap-5">
                    <div className="flex items-center justify-center w-10 h-10 border border-[var(--color-accent-gold)] bg-[var(--color-bg-paper-dark)] rounded shadow-inner">
                        <BookOpen size={20} className="text-[var(--color-accent-gold)]" />
                    </div>
                    <div>
                        <h1 className="text-xl md:text-2xl font-serif font-bold text-[var(--color-ink)] leading-none uppercase tracking-wide">
                            Dossigraphica
                        </h1>
                        <p className="text-[9px] font-mono text-[var(--color-ink-light)] uppercase tracking-[0.2em] mt-1 hidden sm:block">
                            An Atlas of Corporate Intelligence
                        </p>
                    </div>
                </div>

                {/* Company selector + Intel button */}
                <div className="flex items-center gap-3">
                    {/* Company selector */}
                    {companies.length > 1 ? (
                        <div ref={dropdownRef} className="relative">
                            <button
                                onClick={() => setDropdownOpen(!dropdownOpen)}
                                className="flex items-center gap-2.5 px-3.5 py-1.5 border border-[var(--color-border-muted)] hover:border-[var(--color-accent-gold)] hover:bg-[var(--color-bg-paper-dark)] transition-all duration-300 rounded shadow-sm cursor-pointer bg-white text-[var(--color-ink)]"
                            >
                                <span className="text-[9px] font-mono font-bold text-[var(--color-accent-gold)] uppercase tracking-wider">Record</span>
                                <span className="text-xs md:text-sm font-serif font-semibold">
                                    {companyName}
                                </span>
                                <ChevronDown
                                    size={12}
                                    className={`text-[var(--color-ink-light)] transition-transform duration-300 ${dropdownOpen ? 'rotate-180' : ''}`}
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
                        <div className="px-3.5 py-1.5 border border-[var(--color-border-muted)] bg-white rounded shadow-sm flex items-center gap-2.5">
                            <span className="text-[9px] font-mono font-bold text-[var(--color-accent-gold)] uppercase tracking-wider">Record</span>
                            <span className="text-xs md:text-sm font-serif font-semibold text-[var(--color-ink)]">{companyName}</span>
                        </div>
                    )}

                    {/* Intel toggle (The Dossier Button) */}
                    <button
                        onClick={onToggleIntel}
                        disabled={(!hasIntel && !intelLoading) || intelLoading}
                        className={`
                            flex items-center gap-2 px-4 py-1.5 border transition-all duration-300 cursor-pointer font-serif font-semibold text-xs rounded shadow-sm
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
                        <span className="uppercase tracking-wider text-[10px]">
                            {intelLoading ? 'Consulting...' : (!selectedCompany ? 'Global Dossier' : 'View Dossier')}
                        </span>
                    </button>
                </div>
            </div>
        </header>
    )
}

