import { useMemo } from 'react';
import { useAppSelector } from '../store/hooks';

/**
 * Hook that derives visible shape IDs from filtered routes.
 * Route filter → trips → shapes
 */
export function useShapeFilter(): Set<string> | null {
  const selectedRouteIds = useAppSelector((state) => state.map.selectedRouteIds);
  const trips = useAppSelector((state) => state.gtfs.trips);

  return useMemo(() => {
    // If no route filter active, show all shapes (null = no filter)
    if (selectedRouteIds.length === 0) {
      return null;
    }

    const routeIdSet = new Set(selectedRouteIds);
    const visibleShapeIds = new Set<string>();

    // Find all trips for selected routes, collect their shape_ids
    for (const trip of trips) {
      if (routeIdSet.has(trip.route_id) && trip.shape_id) {
        visibleShapeIds.add(trip.shape_id);
      }
    }

    return visibleShapeIds;
  }, [selectedRouteIds, trips]);
}