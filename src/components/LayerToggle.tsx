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
    { id: 'offices', label: 'Offices', icon: Building2, color: '#1a1a1a', type: 'both' },
    { id: 'supplyChain', label: 'Supply Chain', icon: Link2, color: '#a36633', type: 'company' },
    { id: 'customers', label: 'Customers', icon: Users, color: '#2a5a8a', type: 'company' },
    { id: 'risks', label: 'Geopolitical Risks', icon: ShieldAlert, color: '#2563eb', type: 'both' },
    { id: 'chain', label: 'Global Value Chain', icon: Network, color: '#1a1a1a', type: 'global' },
    { id: 'chokepoints', label: 'Systemic Chokepoints', icon: Target, color: '#ef4444', type: 'global' },
]

export default function LayerToggle({ activeLayers, onToggle, hasIntel, viewMode }: LayerToggleProps) {
    const visibleLayers = LAYERS.filter(l => {
        if (viewMode === 'global') return l.type === 'global' || l.type === 'both'
        return l.type === 'company' || l.type === 'both'
    })

    return (
        <div className="absolute bottom-10 right-12 z-40 animate-fade-in">
            <div className="bg-[var(--color-bg-paper)] border-2 border-[var(--color-ink)] p-4 shadow-[4px_4px_0_var(--color-ink)]">
                <p className="text-[10px] uppercase tracking-[0.2em] text-[var(--color-ink-muted)] font-bold mb-4 border-b border-[var(--color-ink)] pb-1">
                    {viewMode === 'global' ? 'Global Layers' : 'Company Layers'}
                </p>
                <div className="flex flex-col gap-2">
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
                                    flex items-center gap-3 text-left transition-all duration-200 cursor-pointer px-2 py-1.5
                                    disabled:opacity-30 disabled:cursor-not-allowed
                                    ${!isDisabled && 'hover:bg-[var(--color-bg-paper-dark)]'}
                                `}
                            >
                                <div
                                    className="w-3 h-3 border border-[var(--color-ink)] flex items-center justify-center"
                                    style={{
                                        background: isActive ? layer.color : 'white',
                                    }}
                                >
                                     {isActive && <div className="w-1 h-1 bg-white rounded-full" />}
                                </div>
                                <Icon size={14} className={isActive ? 'text-[var(--color-ink)]' : 'text-[var(--color-ink-muted)]'} />
                                <span className={`text-xs font-serif font-bold ${isActive ? 'text-[var(--color-ink)]' : 'text-[var(--color-ink-muted)]'}`}>
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
