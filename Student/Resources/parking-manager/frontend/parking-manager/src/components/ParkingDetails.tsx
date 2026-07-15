import React, { useEffect } from 'react';
import { LevelInfo } from '../types';
import './ParkingDetails.css';

interface ParkingDetailsProps {
  city: string;
  levels: LevelInfo[];
  onClose: () => void;
  onUpdateLevel: (levelNumber: number, availableSlots: number) => void;
  onRefresh: () => void;
}

const ParkingDetails: React.FC<ParkingDetailsProps> = ({ city, levels, onClose, onUpdateLevel, onRefresh }) => {
  const [editingLevel, setEditingLevel] = React.useState<number | null>(null);
  const [editValue, setEditValue] = React.useState<string>('');

  // Auto-refresh level details every 3 seconds
  useEffect(() => {
    const interval = setInterval(() => {
      onRefresh();
    }, 3000);

    return () => clearInterval(interval);
  }, [onRefresh]);

  const handleEdit = (level: number, currentValue: number) => {
    setEditingLevel(level);
    setEditValue(currentValue.toString());
  };

  const handleSave = (level: number, totalSlots: number) => {
    const newValue = parseInt(editValue);
    if (isNaN(newValue) || newValue < 0 || newValue > totalSlots) {
      alert(`Please enter a valid number between 0 and ${totalSlots}`);
      return;
    }
    onUpdateLevel(level, newValue);
    setEditingLevel(null);
  };

  const handleCancel = () => {
    setEditingLevel(null);
    setEditValue('');
  };

  const getOccupancyColor = (rate: number): string => {
    if (rate < 50) return '#4caf50';
    if (rate < 80) return '#ff9800';
    return '#f44336';
  };

  return (
    <div className="parking-details-overlay" onClick={onClose}>
      <div className="parking-details-modal" onClick={(e) => e.stopPropagation()}>
        <div className="parking-details-header">
          <h2>🚗 {city} Parking - Level Details</h2>
          <button className="close-btn" onClick={onClose}>✕</button>
        </div>

        <div className="levels-container">
          {levels.map((level) => (
            <div key={level.level} className="level-card">
              <div className="level-header">
                <h3>Level {level.level}</h3>
                <div 
                  className="level-occupancy"
                  style={{ backgroundColor: getOccupancyColor(parseFloat(level.occupancyRate)) }}
                >
                  {level.occupancyRate}% occupied
                </div>
              </div>

              <div className="level-stats">
                <div className="level-stat">
                  <span className="stat-label">Total Slots:</span>
                  <span className="stat-value">{level.totalSlots}</span>
                </div>
                <div className="level-stat">
                  <span className="stat-label">Occupied:</span>
                  <span className="stat-value">{level.occupiedSlots}</span>
                </div>
                <div className="level-stat">
                  <span className="stat-label">Available:</span>
                  {editingLevel === level.level ? (
                    <input
                      type="number"
                      value={editValue}
                      onChange={(e) => setEditValue(e.target.value)}
                      min="0"
                      max={level.totalSlots}
                      className="level-input"
                      autoFocus
                    />
                  ) : (
                    <span className="stat-value available">{level.availableSlots}</span>
                  )}
                </div>
              </div>

              <div className="level-actions">
                {editingLevel === level.level ? (
                  <>
                    <button 
                      className="save-btn"
                      onClick={() => handleSave(level.level, level.totalSlots)}
                    >
                      Save
                    </button>
                    <button 
                      className="cancel-btn"
                      onClick={handleCancel}
                    >
                      Cancel
                    </button>
                  </>
                ) : (
                  <button 
                    className="edit-btn"
                    onClick={() => handleEdit(level.level, level.availableSlots)}
                  >
                    Update Availability
                  </button>
                )}
              </div>

              <div className="level-visual">
                <div className="slots-bar">
                  <div 
                    className="slots-occupied"
                    style={{ 
                      width: `${level.occupancyRate}%`,
                      backgroundColor: getOccupancyColor(parseFloat(level.occupancyRate))
                    }}
                  />
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

export default ParkingDetails;
