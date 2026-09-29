import { useEffect, useRef, useState } from 'react'
import { fmtKm, fmtScore } from './nwisModel.js'

// MapLibre is lazy-loaded here only. No basemap tiles and no network requests: on-prem/offline friendly.
// The backend already filtered the offsets by radius; this component only draws what it returned.
let maplibre = null
async function loadMaplibre() {
  if (!maplibre) {
    const [module] = await Promise.all([import('maplibre-gl'), import('maplibre-gl/dist/maplibre-gl.css')])
    maplibre = module.default || module
  }
  return maplibre
}

const KM_PER_DEG = 111.32
// Display geometry for the ring only (not a distance filter).
function ring(lat, lon, km, steps = 72) {
  const coords = Array.from({ length: steps + 1 }, (_, i) => {
    const a = (i / steps) * Math.PI * 2
    return [lon + (km * Math.sin(a)) / (KM_PER_DEG * Math.cos((lat * Math.PI) / 180)), lat + (km * Math.cos(a)) / KM_PER_DEG]
  })
  return { type: 'Feature', geometry: { type: 'Polygon', coordinates: [coords] }, properties: {} }
}
function graticule(lat, lon, span = 0.4, step = 0.05) {
  const lines = []
  const lat0 = Math.floor((lat - span) / step) * step, lon0 = Math.floor((lon - span) / step) * step
  for (let x = lon0; x <= lon + span; x += step) lines.push([[x, lat - span], [x, lat + span]])
  for (let y = lat0; y <= lat + span; y += step) lines.push([[lon - span, y], [lon + span, y]])
  return { type: 'FeatureCollection', features: lines.map(coordinates => ({ type: 'Feature', geometry: { type: 'LineString', coordinates }, properties: {} })) }
}
const css = name => getComputedStyle(document.documentElement).getPropertyValue(name).trim()
const relevance = total => (total == null ? 'unknown' : total >= 0.75 ? 'high' : total >= 0.55 ? 'medium' : 'low')

export default function NearbyMap({ center, offsets = [], radiusKm, selectedId, onSelect, compact = false, label = 'Nearby wells map' }) {
  const host = useRef(null)
  const map = useRef(null)
  const markers = useRef([])
  const [status, setStatus] = useState('loading')
  const hasCenter = Number.isFinite(center?.lat) && Number.isFinite(center?.lon)

  useEffect(() => {
    if (!hasCenter) return undefined
    let disposed = false
    loadMaplibre().then(lib => {
      if (disposed || !host.current) return
      try {
        const instance = new lib.Map({
          container: host.current, center: [center.lon, center.lat], zoom: 11, attributionControl: false, interactive: !compact,
          style: { version: 8, sources: {}, layers: [{ id: 'bg', type: 'background', paint: { 'background-color': css('--surface-2') || '#f4f7fb' } }] },
        })
        if (!compact) { instance.addControl(new lib.NavigationControl({ showCompass: false }), 'top-right'); instance.addControl(new lib.ScaleControl({ unit: 'metric' }), 'bottom-left') }
        instance.on('load', () => {
          instance.addSource('grid', { type: 'geojson', data: graticule(center.lat, center.lon) })
          instance.addLayer({ id: 'grid', type: 'line', source: 'grid', paint: { 'line-color': css('--line') || '#d6dde6', 'line-width': 1 } })
          instance.addSource('ring', { type: 'geojson', data: ring(center.lat, center.lon, radiusKm) })
          instance.addLayer({ id: 'ring-fill', type: 'fill', source: 'ring', paint: { 'fill-color': css('--ai') || '#1d63d6', 'fill-opacity': 0.06 } })
          instance.addLayer({ id: 'ring-line', type: 'line', source: 'ring', paint: { 'line-color': css('--ai') || '#1d63d6', 'line-width': 1.5, 'line-dasharray': [3, 2] } })
          map.current = instance
          setStatus('ready')
        })
      } catch { setStatus('failed') }
    }).catch(() => !disposed && setStatus('failed'))
    return () => { disposed = true; markers.current.forEach(m => m.remove()); markers.current = []; map.current?.remove(); map.current = null }
    // The map is created once per well; radius and offsets update in place below.
  }, [hasCenter, center?.lat, center?.lon, compact]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const instance = map.current
    if (status !== 'ready' || !instance || !maplibre) return
    const geometry = ring(center.lat, center.lon, radiusKm)
    instance.getSource('ring')?.setData(geometry)
    const bounds = geometry.geometry.coordinates[0].reduce((b, c) => b.extend(c), new maplibre.LngLatBounds(geometry.geometry.coordinates[0][0], geometry.geometry.coordinates[0][0]))
    instance.fitBounds(bounds, { padding: compact ? 12 : 36, duration: window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ? 0 : 500 })
    markers.current.forEach(m => m.remove())
    const make = (lngLat, element) => new maplibre.Marker({ element }).setLngLat(lngLat).addTo(instance)
    const active = document.createElement('div')
    active.className = 'nw-marker nw-marker-active'
    active.setAttribute('role', 'img')
    active.setAttribute('aria-label', `${center.label || center.id} (active well)`)
    active.textContent = center.label || center.id
    const next = [make([center.lon, center.lat], active)]
    for (const o of offsets) {
      if (!Number.isFinite(o.well?.lat) || !Number.isFinite(o.well?.lon)) continue
      const events = Object.values(o.eventCounts || {}).reduce((a, b) => a + b, 0)
      const element = document.createElement(compact ? 'div' : 'button')
      element.className = 'nw-marker'
      element.dataset.relevance = relevance(o.total)
      if (o.id === selectedId) element.dataset.selected = 'true'
      const name = document.createElement('span')
      name.className = 'nw-marker-label'
      name.textContent = o.id
      if (events) { const count = document.createElement('b'); count.textContent = events; name.append(count) }
      const dot = document.createElement('span')
      dot.className = 'nw-marker-dot'
      element.append(dot, name)
      const summary = `${o.id}: rank ${o.rank}, score ${fmtScore(o.total)}, ${fmtKm(o.distanceKm)}, ${events} historical events`
      if (compact) { element.setAttribute('role', 'img'); element.setAttribute('aria-label', summary) }
      else { element.type = 'button'; element.setAttribute('aria-label', summary); element.setAttribute('aria-pressed', String(o.id === selectedId)); element.addEventListener('click', () => onSelect?.(o.id)) }
      next.push(make([o.well.lon, o.well.lat], element))
    }
    markers.current = next
  }, [status, offsets, radiusKm, selectedId, onSelect, center?.lat, center?.lon, center?.id, center?.label, compact])

  if (!hasCenter) return <p className="chart-empty">The active well has no surface coordinates, so the map cannot be drawn.</p>
  return <div className={`nw-map${compact ? ' is-compact' : ''}`}>
    <div ref={host} className="nw-map-canvas" role="region" aria-label={`${label}. Offset wells are also listed in the table.`} />
    {status === 'loading' && <p className="nw-map-note" role="status">Loading map…</p>}
    {status === 'failed' && <p className="nw-map-note">The map needs WebGL, which is unavailable here. Every offset is listed in the table.</p>}
    {!compact && status === 'ready' && <p className="nw-map-legend" aria-hidden="true"><span data-relevance="high" />High relevance <span data-relevance="medium" />Medium <span data-relevance="low" />Low · number = historical events · no basemap tiles (offline)</p>}
  </div>
}
