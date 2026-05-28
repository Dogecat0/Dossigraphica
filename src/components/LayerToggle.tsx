import { useState, useEffect } from 'react'
import {
    Building2, Link2, Users, ShieldAlert, Network, Target, Layers, X, DollarSign
} from 'lucide-react'
import type { LayerName } from '../types'

interface LayerToggleProps {
    activeLayers: Set<LayerName>
    onToggle: (layer: LayerName) => void
    hasIntel: boolean
    viewMode: 'global' | 'company'
}

const LAYERS: { id: LayerName; label: string; icon: any; color: string; type: 'company' | 'global' | 'both' }[] = [
    { id: 'offices', label: 'Offices', icon: Building2, color: '#c5a880', type: 'both' }, // Gold
    { id: 'supplyChain', label: 'Supply Chain', icon: Link2, color: '#c5a880', type: 'company' }, // Gold
    { id: 'customers', label: 'Customers', icon: Users, color: '#1f486d', type: 'company' }, // Blue
    { id: 'risks', label: 'Geopolitical Risks', icon: ShieldAlert, color: '#c2593f', type: 'both' }, // Rust
    { id: 'chain', label: 'Global Value Chain', icon: Network, color: '#2e4d3a', type: 'global' }, // Sage
    { id: 'chokepoints', label: 'Systemic Chokepoints', icon: Target, color: '#8f331d', type: 'global' }, // Rust Red
    { id: 'institutionalHoldings', label: 'Institutional Holdings', icon: DollarSign, color: '#c5a880', type: 'both' }, // Gold
]

export default function LayerToggle({ activeLayers, onToggle, hasIntel, viewMode }: LayerToggleProps) {
    const [isExpanded, setIsExpanded] = useState(true)

    useEffect(() => {
        const handleResize = () => {
            // Keep state synchronous on resize if needed
        }
        window.addEventListener('resize', handleResize)
        return () => window.removeEventListener('resize', handleResize)
    }, [])

    const visibleLayers = LAYERS.filter(l => {
        if (viewMode === 'global') return l.type === 'global' || l.type === 'both'
        return l.type === 'company' || l.type === 'both'
    })

    if (!isExpanded) {
        return (
            <div className="absolute top-[80px] left-6 max-md:top-[68px] max-md:left-4 z-40 animate-fade-in">
                <button
                    onClick={() => setIsExpanded(true)}
                    title="Layers Legend"
                    className="w-12 h-12 bg-[var(--color-ink)] border-2 border-[var(--color-accent-gold)] rounded-full shadow-[var(--shadow-executive-lg)] hover:bg-[var(--color-ink-muted)] transition-all duration-300 cursor-pointer flex items-center justify-center text-[var(--color-accent-gold)] hover:text-white"
                >
                    <Layers size={20} />
                </button>
            </div>
        )
    }

    return (
        <div className="absolute top-[80px] left-6 max-md:top-[68px] max-md:left-4 z-40 animate-fade-in">
            <div className="bg-[var(--color-bg-paper)] border border-[var(--color-border-muted)] border-t-2 border-t-[var(--color-accent-gold)] p-3 md:p-4 shadow-[var(--shadow-executive-lg)] rounded w-auto max-md:min-w-0 md:w-64">
                <div className="flex items-center justify-between border-b border-[var(--color-border-muted)] pb-1.5 mb-2 md:mb-3 gap-3">
                    <p className="text-[9px] uppercase tracking-[0.15em] text-[var(--color-accent-gold)] font-mono font-bold">
                        {viewMode === 'global' ? 'Global Analysis Layers' : 'Company Dossier Layers'}
                    </p>
                    <button
                        onClick={() => setIsExpanded(false)}
                        title="Minimize"
                        className="text-[var(--color-ink-light)] hover:text-[var(--color-ink)] hover:bg-[var(--color-bg-paper-dark)]/50 p-1 rounded transition-colors duration-200 cursor-pointer flex-shrink-0"
                    >
                        <X size={13} />
                    </button>
                </div>
                <div className="flex flex-col max-md:grid max-md:grid-cols-2 max-md:gap-x-3 max-md:gap-y-1 gap-1">
                    {visibleLayers.map(layer => {
                        const Icon = layer.icon
                        const isActive = activeLayers.has(layer.id)
                        const isDisabled = layer.type === 'company' && layer.id !== 'offices' && !hasIntel

                        return (
                            <button
                                key={layer.id}
                                onClick={() => !isDisabled && onToggle(layer.id)}
                                disabled={isDisabled}
                                className={`
                                    flex items-center gap-2 md:gap-3 text-left transition-all duration-200 cursor-pointer px-1.5 py-1 md:px-2 md:py-1.5 rounded
                                    disabled:opacity-30 disabled:cursor-not-allowed
                                    ${!isDisabled && 'hover:bg-[var(--color-bg-paper-dark)]/50 hover:text-[var(--color-ink)]'}
                                `}
                            >
                                <div
                                    className="w-3.5 h-3.5 border rounded-sm flex items-center justify-center transition-all duration-200 flex-shrink-0"
                                    style={{
                                        borderColor: isActive ? layer.color : 'var(--color-border-muted)',
                                        backgroundColor: isActive ? 'var(--color-ink)' : 'white',
                                    }}
                                >
                                     {isActive && (
                                         <div 
                                             className="w-1.5 h-1.5 rounded-sm"
                                             style={{ backgroundColor: layer.color }}
                                         />
                                     )}
                                </div>
                                <Icon size={13} className={`flex-shrink-0 ${isActive ? 'text-[var(--color-ink)]' : 'text-[var(--color-ink-light)]'}`} />
                                <span className={`text-[11px] md:text-xs font-serif font-bold truncate ${isActive ? 'text-[var(--color-ink)]' : 'text-[var(--color-ink-light)]'}`}>
                                    {layer.id === 'offices' && viewMode === 'global' ? 'Headquarters' : layer.label}
                                </span>
                            </button>
                        )
                    })}
                </div>
            </div>
        </div>
    )
}
