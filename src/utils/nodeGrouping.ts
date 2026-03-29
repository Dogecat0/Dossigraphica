export interface GeoPoint {
    lat: number
    lng: number
}

/**
 * Groups items by geographic proximity and assigns each item a stackIndex
 * and stackTotal so the rendering layer can apply screen-space pixel offsets
 * to fan out overlapping nodes without distorting their real coordinates.
 *
 * @param items - Array of objects with lat/lng properties.
 * @param threshold - Max distance in degrees to consider two points overlapping.
 *                    0.5° ≈ 55 km at the equator — tight enough for city-level overlap.
 * @returns A new array with `stackIndex` and `stackTotal` appended to each item.
 */
export function assignStackPositions<T extends GeoPoint>(
    items: T[],
    threshold: number = 0.5
): (T & { stackIndex: number; stackTotal: number })[] {
    // Build clusters using simple greedy proximity grouping
    const clusters: number[][] = [] // each cluster is an array of indices
    const assigned = new Set<number>()

    for (let i = 0; i < items.length; i++) {
        if (assigned.has(i)) continue

        const cluster = [i]
        assigned.add(i)

        for (let j = i + 1; j < items.length; j++) {
            if (assigned.has(j)) continue

            const dLat = items[i].lat - items[j].lat
            const dLng = items[i].lng - items[j].lng
            const distSq = dLat * dLat + dLng * dLng

            if (distSq < threshold * threshold) {
                cluster.push(j)
                assigned.add(j)
            }
        }

        clusters.push(cluster)
    }

    // Build output with stack metadata
    const result = items.map(item => ({
        ...item,
        stackIndex: 0,
        stackTotal: 1,
    }))

    for (const cluster of clusters) {
        const total = cluster.length
        if (total <= 1) continue

        cluster.forEach((itemIndex, positionInCluster) => {
            result[itemIndex].stackTotal = total
            result[itemIndex].stackIndex = positionInCluster
        })
    }

    return result
}

/**
 * Calculates a pixel offset for a node within a stack.
 * Returns { dx, dy } in pixels to apply as CSS transform.
 *
 * - 1 node: no offset
 * - 2 nodes: side-by-side horizontally (±8px)
 * - 3+ nodes: arranged in a small circle (radius ~12px)
 */
export function getStackOffset(
    stackIndex: number,
    stackTotal: number,
    radius: number = 12
): { dx: number; dy: number } {
    if (stackTotal <= 1) return { dx: 0, dy: 0 }

    if (stackTotal === 2) {
        // Side-by-side, offset horizontally
        return { dx: stackIndex === 0 ? -8 : 8, dy: 0 }
    }

    // Radial layout for 3+
    const angle = (stackIndex / stackTotal) * Math.PI * 2 - Math.PI / 2 // start from top
    return {
        dx: Math.cos(angle) * radius,
        dy: Math.sin(angle) * radius,
    }
}
