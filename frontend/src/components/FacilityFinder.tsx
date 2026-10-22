import { useEffect, useRef, useState } from 'react'
import {
  Alert,
  Box,
  Button,
  CircularProgress,
  MenuItem,
  TextField,
  Typography,
} from '@mui/material'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { useTranslation } from 'react-i18next'
import { facilitiesApi, referenceApi } from '../api/endpoints'
import type { Facility, FacilitiesResponse } from '../api/types'

type Coordinate = { lat: number; lon: number }

/** Nearest facilities: geolocation after an explanation, district/pincode fallback. */
export function FacilityFinder({ district }: { district?: string }) {
  const { t } = useTranslation()
  const [mode, setMode] = useState<'ask' | 'locating' | 'ready' | 'fallback'>('ask')
  const [data, setData] = useState<FacilitiesResponse | null>(null)
  const [coords, setCoords] = useState<Coordinate | null>(null)
  const [error, setError] = useState(false)
  const [pincode, setPincode] = useState('')
  const [selectedDistrict, setSelectedDistrict] = useState(district ?? '')
  const [districtOptions, setDistrictOptions] = useState<string[]>(
    district ? [district] : []
  )

  useEffect(() => {
    let cancelled = false
    referenceApi
      .locations()
      .then((locations) => {
        if (!cancelled) {
          setDistrictOptions(locations.districts_by_state['Tamil Nadu'] ?? [])
        }
      })
      .catch(() => {
        if (!cancelled && district) {
          setDistrictOptions([district])
        }
      })
    return () => {
      cancelled = true
    }
  }, [district])

  const search = async (
    params: Coordinate | { district: string } | { pincode: string }
  ) => {
    setMode('locating')
    setError(false)
    try {
      let response: FacilitiesResponse
      if ('lat' in params) {
        response = await facilitiesApi.nearest({ lat: params.lat, lon: params.lon, limit: 10 })
        setCoords({ lat: params.lat, lon: params.lon })
      } else {
        response = await facilitiesApi.byDistrict({ ...params, limit: 10 })
        setCoords(null)
      }
      setData(response)
      setMode('ready')
    } catch {
      setError(true)
      setMode('ask')
    }
  }

  const locate = () => {
    if (!('geolocation' in navigator)) {
      setMode('fallback')
      return
    }
    setMode('locating')
    navigator.geolocation.getCurrentPosition(
      (position) =>
        void search({ lat: position.coords.latitude, lon: position.coords.longitude }),
      () => setMode('fallback'),
      { timeout: 8000 }
    )
  }

  if (mode === 'locating') {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}>
        <CircularProgress aria-label={t('common.loading')} />
      </Box>
    )
  }

  if (mode === 'fallback') {
    return (
      <Box sx={{ display: 'grid', gap: 2 }}>
        <Typography>{t('facilities.explain')}</Typography>
        <TextField
          select
          label={t('onboarding.district')}
          value={selectedDistrict}
          onChange={(event) => setSelectedDistrict(event.target.value)}
          fullWidth
        >
          {districtOptions.map((name) => (
            <MenuItem key={name} value={name}>
              {name}
            </MenuItem>
          ))}
        </TextField>
        <TextField
          label={t('onboarding.pincode')}
          value={pincode}
          onChange={(event) => setPincode(event.target.value)}
          inputProps={{ inputMode: 'numeric', maxLength: 6, 'data-testid': 'facility-pincode' }}
          fullWidth
        />
        <Button
          variant="contained"
          disabled={selectedDistrict.trim() === '' && pincode.trim().length !== 6}
          onClick={() =>
            void (selectedDistrict.trim()
              ? search({ district: selectedDistrict.trim() })
              : search({ pincode: pincode.trim() }))
          }
          sx={{ minHeight: 48 }}
          data-testid="facility-search"
        >
          {t('facilities.search')}
        </Button>
        <Button onClick={() => setMode('ask')} sx={{ minHeight: 48, color: 'darkgreen' }}>
          {t('common.back')}
        </Button>
      </Box>
    )
  }

  if (mode === 'ready' && data) {
    return <FacilityList data={data} coords={coords} onRetry={() => setMode('fallback')} />
  }

  return (
    <Box sx={{ display: 'grid', gap: 2 }}>
      {error ? <Alert severity="warning">{t('facilities.loadError')}</Alert> : null}
      <Typography>{t('facilities.explain')}</Typography>
      <Button variant="contained" onClick={locate} sx={{ minHeight: 48 }}>
        {t('facilities.useLocation')}
      </Button>
      <Button onClick={() => setMode('fallback')} sx={{ minHeight: 48, color: 'darkgreen' }}>
        {t('facilities.enterManually')}
      </Button>
    </Box>
  )
}

function FacilityList({
  data,
  coords,
  onRetry,
}: {
  data: FacilitiesResponse
  coords: Coordinate | null
  onRetry: () => void
}) {
  const { t } = useTranslation()
  if (data.facilities.length === 0) {
    return (
      <Box sx={{ display: 'grid', gap: 2 }}>
        <Typography>{t('facilities.none')}</Typography>
        <Button onClick={onRetry} sx={{ minHeight: 48, color: 'darkgreen' }}>
          {t('common.back')}
        </Button>
      </Box>
    )
  }
  const first = data.facilities[0]
  const center: [number, number] =
    coords !== null
      ? [coords.lat, coords.lon]
      : first.lat !== null && first.lon !== null
        ? [first.lat, first.lon]
        : [11.0, 78.7]
  return (
    <Box sx={{ display: 'grid', gap: 2 }}>
      <Typography variant="h6">{t('facilities.title')}</Typography>
      <MapPanel facilities={data.facilities} center={center} />
      {data.facilities.map((facility) => (
        <FacilityCard key={facility.id} facility={facility} />
      ))}
    </Box>
  )
}

function FacilityCard({ facility }: { facility: Facility }) {
  const { t } = useTranslation()
  return (
    <Box
      data-testid="facility-item"
      data-ui="facility-finder"
      sx={{ p: 2, border: '1px solid lightgray', borderRadius: 1 }}
    >
      <Typography fontWeight={700}>{facility.name}</Typography>
      <Typography color="text.secondary">
        {t(`facilities.type.${facility.type}`)}
        {facility.distance_km !== null ? `, ${facility.distance_km} km` : ''}
      </Typography>
      <Typography>{facility.address}</Typography>
      {facility.working_hours ? (
        <Typography color="text.secondary">{facility.working_hours}</Typography>
      ) : null}
      <Box sx={{ display: 'flex', gap: 2, mt: 1 }}>
        {facility.phone ? (
          <Button component="a" href={`tel:${facility.phone}`} sx={{ minHeight: 44, px: 1 }}>
            {t('facilities.call')}
          </Button>
        ) : null}
        {facility.lat !== null && facility.lon !== null ? (
          <Button
            component="a"
            target="_blank"
            rel="noreferrer"
            href={`https://www.google.com/maps/dir/?api=1&destination=${facility.lat},${facility.lon}`}
            sx={{ minHeight: 44, px: 1 }}
          >
            {t('facilities.directions')}
          </Button>
        ) : null}
      </Box>
    </Box>
  )
}

function MapPanel({
  facilities,
  center,
}: {
  facilities: Facility[]
  center: [number, number]
}) {
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!containerRef.current) return
    const points = facilities.filter(
      (facility) => facility.lat !== null && facility.lon !== null
    ) as (Facility & { lat: number; lon: number })[]
    const map = L.map(containerRef.current, {
      scrollWheelZoom: false,
    })
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; OpenStreetMap contributors',
    }).addTo(map)
    if (points.length > 0) {
      const markers = points.map((point) => {
        const marker = L.circleMarker([point.lat, point.lon], {
          radius: 9,
          color: 'darkgreen',
          fillColor: 'seagreen',
          fillOpacity: 0.9,
        }).addTo(map)
        marker.bindTooltip(point.name)
        return marker
      })
      const group = L.featureGroup(markers)
      map.fitBounds(group.getBounds().pad(0.35))
    } else {
      map.setView(center, 10)
    }
    return () => {
      map.remove()
    }
  }, [facilities, center])

  return (
    <Box
      ref={containerRef}
      data-testid="facility-map"
      sx={{
        height: 280,
        borderRadius: 2,
        border: '1px solid lightgray',
        '& img': { maxWidth: 'none' },
      }}
    />
  )
}
