import { useEffect } from 'react';
import { useMap } from 'react-map-gl/maplibre';
import { useAppSelector } from '../../../store/hooks';
import { useShapeFilter } from '../../../hooks/useShapeFilter';

const SHAPE_SOURCE_ID = 'shapes-source';
const SHAPE_LAYER_ID = 'shapes-layer';

export function ShapeLayer() {
  const { current: map } = useMap();
  const shapes = useAppSelector((state) => state.gtfs.shapes);
  const visibleShapeIds = useShapeFilter();

  useEffect(() => {
    if (!map) return;

    // Build GeoJSON from shapes, filtering if needed
    const features = shapes
      .filter((shape) => {
        // If no filter active, include all
        if (visibleShapeIds === null) return true;
        return visibleShapeIds.has(shape.shape_id);
      })
      .map((shape) => ({
        type: 'Feature' as const,
        properties: { shape_id: shape.shape_id },
        geometry: {
          type: 'LineString' as const,
          coordinates: shape.points.map((pt) => [pt.shape_pt_lon, pt.shape_pt_lat]),
        },
      }));

    const geojson = {
      type: 'FeatureCollection' as const,
      features,
    };

    // Update or create source
    const source = map.getSource(SHAPE_SOURCE_ID);
    if (source && 'setData' in source) {
      source.setData(geojson);
    } else {
      map.addSource(SHAPE_SOURCE_ID, {
        type: 'geojson',
        data: geojson,
      });

      map.addLayer({
        id: SHAPE_LAYER_ID,
        type: 'line',
        source: SHAPE_SOURCE_ID,
        paint: {
          'line-color': '#3b82f6',
          'line-width': 3,
          'line-opacity': 0.8,
        },
      });
    }
  }, [map, shapes, visibleShapeIds]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (map) {
        if (map.getLayer(SHAPE_LAYER_ID)) map.removeLayer(SHAPE_LAYER_ID);
        if (map.getSource(SHAPE_SOURCE_ID)) map.removeSource(SHAPE_SOURCE_ID);
      }
    };
  }, [map]);

  return null;
}