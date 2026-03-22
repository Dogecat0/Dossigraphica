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
        <header className="z-40 bg-[var(--color-bg-paper)] border-b-2 border-[var(--color-ink)] animate-fade-in">
            <div className="flex items-center justify-between px-8 py-4">
                {/* Logo + Title (The Masthead) */}
                <div className="flex items-center gap-6">
                    <div className="flex items-center justify-center w-12 h-12 border-2 border-[var(--color-ink)] bg-white">
                        <BookOpen size={24} className="text-[var(--color-ink)]" />
                    </div>
                    <div>
                        <h1 className="text-2xl font-serif font-bold text-[var(--color-ink)] leading-none uppercase tracking-tighter">
                            Dossigraphica
                        </h1>
                        <p className="text-[10px] font-mono font-bold text-[var(--color-ink-muted)] uppercase tracking-widest mt-1">
                            An Atlas of Corporate Intelligence
                        </p>
                    </div>
                </div>

                {/* Company selector + Intel button */}
                <div className="flex items-center gap-4">
                    {/* Company selector */}
                    {companies.length > 1 ? (
                        <div ref={dropdownRef} className="relative">
                            <button
                                onClick={() => setDropdownOpen(!dropdownOpen)}
                                className="flex items-center gap-3 px-4 py-2 border border-[var(--color-ink)] hover:bg-[var(--color-ink)] hover:text-white transition-all cursor-pointer bg-white"
                            >
                                <span className="text-[10px] font-mono font-bold opacity-60 uppercase">Record</span>
                                <span className="text-sm font-serif font-bold">
                                    {companyName}
                                </span>
                                <ChevronDown
                                    size={14}
                                    className={`transition-transform ${dropdownOpen ? 'rotate-180' : ''}`}
                                />
                            </button>

                            {dropdownOpen && (
                                <div className="absolute right-0 top-full mt-1 w-72 bg-[var(--color-bg-paper)] border-2 border-[var(--color-ink)] shadow-[4px_4px_0_var(--color-ink)] z-50 max-h-[80vh] overflow-y-auto">
                                    {/* Global View Option */}
                                    <button
                                        onClick={() => {
                                            setSelectedCompany(null)
                                            setSelectedOfficeId(null)
                                            setIsIntelPanelOpen(false)
                                            setDropdownOpen(false)
                                        }}
                                        className={`
                                            w-full text-left px-4 py-3 border-b-2 border-[var(--color-ink)]
                                            transition-colors cursor-pointer
                                            ${!selectedCompany 
                                                ? 'bg-[var(--color-bg-paper-dark)]' 
                                                : 'hover:bg-[var(--color-ink)] hover:text-white'
                                            }
                                        `}
                                    >
                                        <div className="flex justify-between items-start">
                                            <div>
                                                <p className="text-sm font-serif font-bold">Global Value Chain</p>
                                                <p className="text-[9px] font-mono uppercase tracking-wider opacity-70">
                                                    Macro Analysis · Cross-Company
                                                </p>
                                            </div>
                                            <span className="text-[9px] font-mono font-bold px-1.5 py-0.5 border border-current">
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
                                                w-full text-left px-4 py-3 border-b border-[var(--color-border-muted)]
                                                transition-colors cursor-pointer last:border-none
                                                ${selectedCompany?.company === company.company
                                                    ? 'bg-[var(--color-bg-paper-dark)]'
                                                    : 'hover:bg-[var(--color-ink)] hover:text-white'
                                                }
                                            `}
                                        >
                                            <div className="flex justify-between items-start">
                                                <div>
                                                    <p className="text-sm font-serif font-bold">{company.company}</p>
                                                    <p className="text-[9px] font-mono uppercase tracking-wider opacity-70">
                                                        {company.ticker} · {company.sector}
                                                    </p>
                                                </div>
                                                <span className="text-[9px] font-mono font-bold px-1.5 py-0.5 border border-current">
                                                    {company.offices.length}
                                                </span>
                                            </div>
                                        </button>
                                    ))}
                                </div>
                            )}
                        </div>
                    ) : (
                        <div className="px-4 py-2 border border-[var(--color-ink)] bg-white flex items-center gap-3">
                            <span className="text-[10px] font-mono font-bold opacity-60 uppercase">Record</span>
                            <span className="text-sm font-serif font-bold">{companyName}</span>
                        </div>
                    )}

                    {/* Intel toggle (The Dossier Button) */}
                    <button
                        onClick={onToggleIntel}
                        disabled={(!hasIntel && !intelLoading) || intelLoading}
                        className={`
                            flex items-center gap-2 px-5 py-2 border-2 transition-all cursor-pointer font-serif font-bold
                            disabled:opacity-30 disabled:cursor-not-allowed
                            ${intelOpen
                                ? 'bg-[var(--color-ink)] border-[var(--color-ink)] text-white shadow-[4px_4px_0_rgba(0,0,0,0.2)]'
                                : 'bg-white border-[var(--color-ink)] text-[var(--color-ink)] hover:shadow-[4px_4px_0_var(--color-ink)] active:translate-x-0.5 active:translate-y-0.5'
                            }
                        `}
                    >
                        {intelLoading ? (
                            <Loader2 size={16} className="animate-spin" />
                        ) : (
                            <Brain size={16} />
                        )}
                        <span className="text-sm uppercase tracking-tight">
                            {intelLoading ? 'Consulting...' : (!selectedCompany ? 'Global Dossier' : 'View Dossier')}
                        </span>
                    </button>
                </div>
            </div>
        </header>
    )
}

