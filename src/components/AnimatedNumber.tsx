import { useEffect, useState, useRef } from 'react'

interface AnimatedNumberProps {
    value: number | null
    formatter: (val: number | null) => string
    duration?: number
}

export default function AnimatedNumber({ value, formatter, duration = 1000 }: AnimatedNumberProps) {
    const [displayValue, setDisplayValue] = useState(value === null ? null : 0)
    const prevValueRef = useRef<number | null>(0)

    useEffect(() => {
        if (value === null) {
            setDisplayValue(null)
            prevValueRef.current = null
            return
        }

        const startValue = prevValueRef.current || 0
        const endValue = value
        let startTimestamp: number | null = null
        let animationFrame: number

        const step = (timestamp: number) => {
            if (!startTimestamp) startTimestamp = timestamp
            const progress = Math.min((timestamp - startTimestamp) / duration, 1)
            
            // easeOutQuart
            const easeProgress = 1 - Math.pow(1 - progress, 4)
            const current = startValue + (endValue - startValue) * easeProgress

            setDisplayValue(current)

            if (progress < 1) {
                animationFrame = window.requestAnimationFrame(step)
            } else {
                setDisplayValue(endValue)
                prevValueRef.current = endValue
            }
        }

        animationFrame = window.requestAnimationFrame(step)
        return () => window.cancelAnimationFrame(animationFrame)
    }, [value, duration])

    return <span>{formatter(displayValue)}</span>
}
