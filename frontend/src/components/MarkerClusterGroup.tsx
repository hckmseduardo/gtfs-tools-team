import { createPathComponent } from '@react-leaflet/core'
import L from 'leaflet'
import 'leaflet.markercluster'
import 'leaflet.markercluster/dist/MarkerCluster.css'
import 'leaflet.markercluster/dist/MarkerCluster.Default.css'
import { ReactNode } from 'react'

export interface MarkerClusterGroupProps {
  children?: ReactNode
  chunkedLoading?: boolean
  maxClusterRadius?: number
  spiderfyOnMaxZoom?: boolean
  showCoverageOnHover?: boolean
  zoomToBoundsOnClick?: boolean
  disableClusteringAtZoom?: number
  singleMarkerMode?: boolean
  spiderfyDistanceMultiplier?: number
  animate?: boolean
  animateAddingMarkers?: boolean
  removeOutsideVisibleBounds?: boolean
}

// Create a custom MarkerClusterGroup component for react-leaflet v4
const MarkerClusterGroup = createPathComponent<L.MarkerClusterGroup, MarkerClusterGroupProps>(
  function createMarkerClusterGroup({ children: _children, ...props }, ctx) {
    const clusterProps = {
      chunkedLoading: props.chunkedLoading ?? true,
      maxClusterRadius: props.maxClusterRadius ?? 50,
      spiderfyOnMaxZoom: props.spiderfyOnMaxZoom ?? true,
      showCoverageOnHover: props.showCoverageOnHover ?? false,
      zoomToBoundsOnClick: props.zoomToBoundsOnClick ?? true,
      disableClusteringAtZoom: props.disableClusteringAtZoom,
      singleMarkerMode: props.singleMarkerMode ?? false,
      spiderfyDistanceMultiplier: props.spiderfyDistanceMultiplier ?? 1,
      animate: props.animate ?? true,
      animateAddingMarkers: props.animateAddingMarkers ?? false,
      removeOutsideVisibleBounds: props.removeOutsideVisibleBounds ?? true,
    }
    const instance = L.markerClusterGroup(clusterProps)
    return { instance, context: { ...ctx, layerContainer: instance } }
  },
  function updateMarkerClusterGroup(_instance, _props, _prevProps) {
    // MarkerClusterGroup options cannot be updated after creation
    // To change options, the component needs to be remounted
  }
)

export default MarkerClusterGroup
