import {
    Building2, Link2, Users, ShieldAlert, Network, Target
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
]

export default function LayerToggle({ activeLayers, onToggle, hasIntel, viewMode }: LayerToggleProps) {
    const visibleLayers = LAYERS.filter(l => {
        if (viewMode === 'global') return l.type === 'global' || l.type === 'both'
        return l.type === 'company' || l.type === 'both'
    })

    return (
        <div className="absolute bottom-10 right-12 max-md:bottom-6 max-md:right-6 z-40 animate-fade-in">
            <div className="bg-[var(--color-bg-paper)] border border-[var(--color-border-muted)] border-t-2 border-t-[var(--color-accent-gold)] p-4 shadow-[var(--shadow-executive-lg)] rounded w-64">
                <p className="text-[9px] uppercase tracking-[0.15em] text-[var(--color-accent-gold)] font-mono font-bold mb-3 border-b border-[var(--color-border-muted)] pb-1.5">
                    {viewMode === 'global' ? 'Global Analysis Layers' : 'Company Dossier Layers'}
                </p>
                <div className="flex flex-col gap-1">
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
                                    flex items-center gap-3 text-left transition-all duration-200 cursor-pointer px-2 py-1.5 rounded
                                    disabled:opacity-30 disabled:cursor-not-allowed
                                    ${!isDisabled && 'hover:bg-[var(--color-bg-paper-dark)]/50 hover:text-[var(--color-ink)]'}
                                `}
                            >
                                <div
                                    className="w-3.5 h-3.5 border rounded-sm flex items-center justify-center transition-all duration-200"
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
                                <Icon size={14} className={isActive ? 'text-[var(--color-ink)]' : 'text-[var(--color-ink-light)]'} />
                                <span className={`text-xs font-serif font-bold ${isActive ? 'text-[var(--color-ink)]' : 'text-[var(--color-ink-light)]'}`}>
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
