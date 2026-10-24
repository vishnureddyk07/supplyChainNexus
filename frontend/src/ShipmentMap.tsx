import { Fragment } from "react";
import {
  CircleMarker,
  MapContainer,
  Polyline,
  Popup,
  TileLayer,
} from "react-leaflet";
import type { Shipment } from "./api";

type ShipmentMapProps = {
  shipments: Shipment[];
  onSelect: (shipmentId: string) => void;
};

export default function ShipmentMap({ shipments, onSelect }: ShipmentMapProps) {
  const points = shipments.flatMap((shipment) => [
    [shipment.origin_latitude, shipment.origin_longitude] as [number, number],
    [shipment.destination_latitude, shipment.destination_longitude] as [number, number],
  ]);
  const center: [number, number] = points.length
    ? [
        points.reduce((sum, point) => sum + point[0], 0) / points.length,
        points.reduce((sum, point) => sum + point[1], 0) / points.length,
      ]
    : [20, 0];

  return (
    <MapContainer className="shipment-map" center={center} zoom={3} scrollWheelZoom>
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      {shipments.map((shipment) => {
        const origin: [number, number] = [
          shipment.origin_latitude,
          shipment.origin_longitude,
        ];
        const destination: [number, number] = [
          shipment.destination_latitude,
          shipment.destination_longitude,
        ];
        return (
          <Fragment key={shipment.shipment_id}>
            <Polyline positions={[origin, destination]} pathOptions={{ color: "#57d3c3", opacity: 0.65 }} />
            <CircleMarker center={origin} radius={6} pathOptions={{ color: "#57d3c3" }}>
              <Popup>
                <button onClick={() => onSelect(shipment.shipment_id)}>
                  {shipment.shipment_id} · {shipment.origin_name}
                </button>
              </Popup>
            </CircleMarker>
            <CircleMarker center={destination} radius={6} pathOptions={{ color: "#83a9ff" }}>
              <Popup>
                <button onClick={() => onSelect(shipment.shipment_id)}>
                  {shipment.shipment_id} · {shipment.destination_name}
                </button>
              </Popup>
            </CircleMarker>
          </Fragment>
        );
      })}
    </MapContainer>
  );
}
