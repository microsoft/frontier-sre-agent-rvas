import React from 'react';
import { ParkingMetrics } from '../types';
import './ParkingCard.css';

interface ParkingCardProps {
  metrics: ParkingMetrics;
  parkingInfo: {
    name: string;
    location: string;
  };
  onViewDetails: () => void;
}

const ParkingCard: React.FC<ParkingCardProps> = ({ metrics, parkingInfo, onViewDetails }) => {
  const getOccupancyColor = (rate: number): string => {
    if (rate < 50) return '#4caf50'; // Green
    if (rate < 80) return '#ff9800'; // Orange
    return '#f44336'; // Red
  };

  return (
    <div className="parking-card">
      <div className="parking-card-header">
        <h2>🚗 {metrics.city}</h2>
        <span className="parking-status" style={{ backgroundColor: metrics.totalAvailable > 0 ? '#4caf50' : '#f44336' }}>
          {metrics.totalAvailable > 0 ? 'Open' : 'Full'}
        </span>
      </div>
      
      <div className="parking-location">
        <p>📍 {parkingInfo.location}</p>
      </div>

      <div className="parking-stats">
        <div className="stat-item">
          <div className="stat-label">Available Slots</div>
          <div className="stat-value">{metrics.totalAvailable} / {metrics.totalSlots}</div>
        </div>
        
        <div className="stat-item">
          <div className="stat-label">Occupancy Rate</div>
          <div 
            className="stat-value" 
            style={{ color: getOccupancyColor(metrics.occupancyRate) }}
          >
            {metrics.occupancyRate.toFixed(1)}%
          </div>
        </div>

        <div className="stat-item">
          <div className="stat-label">Levels</div>
          <div className="stat-value">{metrics.numberOfLevels}</div>
        </div>
      </div>

      <div className="parking-facilities">
        <div className="facility-item">
          <span>🚻 WC: {metrics.availableWC}</span>
        </div>
        <div className="facility-item">
          <span>⚡ Chargers: {metrics.availableElectricChargers}</span>
        </div>
        <div className="facility-item">
          <span>🕐 {metrics.workingHours.open} - {metrics.workingHours.close}</span>
        </div>
      </div>

      <button className="view-details-btn" onClick={onViewDetails}>
        View Details
      </button>

      <div className="last-updated">
        Last updated: {new Date(metrics.lastUpdated).toLocaleString()}
      </div>
    </div>
  );
};

export default ParkingCard;
