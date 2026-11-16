/**
 * Windows Event Source Installation Script
 * 
 * Run this script with administrator privileges on Windows to register
 * the event source in Windows Event Viewer.
 * 
 * Usage: node install-event-source.js
 * 
 * Note: This script requires administrator privileges on Windows
 */

require('dotenv').config();

const eventSource = process.env.EVENT_LOG_SOURCE || 'MadridParkingAPI';
const eventLog = process.env.EVENT_LOG_NAME || 'Application';

console.log('===========================================');
console.log('Madrid Parking API - Event Source Installer');
console.log('===========================================\n');

console.log(`Event Source: ${eventSource}`);
console.log(`Event Log: ${eventLog}\n`);

// Check if running on Windows
if (process.platform !== 'win32') {
  console.log('❌ This script must be run on Windows.');
  console.log('   The API will use console logging on non-Windows systems.');
  process.exit(0);
}

// Try to load node-windows
let EventLogger;
try {
  EventLogger = require('node-windows').EventLogger;
} catch (error) {
  console.log('❌ node-windows module not found.');
  console.log('   Please install it first: npm install node-windows');
  process.exit(1);
}

console.log('Installing Windows Event Source...\n');
console.log('⚠️  NOTE: This operation requires administrator privileges.');
console.log('   If you see permission errors, please run this script as Administrator.\n');

try {
  // Create a logger instance - this will register the event source
  const logger = new EventLogger(eventSource);
  
  // Test the logger
  logger.info('Madrid Parking API - Event Source Installed Successfully');
  
  console.log('✅ Event source installed successfully!');
  console.log(`\nYou can now view logs in Windows Event Viewer:`);
  console.log(`   1. Open Event Viewer (eventvwr.msc)`);
  console.log(`   2. Navigate to: Windows Logs > ${eventLog}`);
  console.log(`   3. Look for events from source: ${eventSource}\n`);
  
  process.exit(0);
} catch (error) {
  console.error('❌ Failed to install event source:', error.message);
  console.error('\nPossible solutions:');
  console.error('   1. Run this script as Administrator');
  console.error('   2. Ensure you have permission to write to the Windows Registry');
  console.error('   3. Check Windows Event Log service is running\n');
  
  process.exit(1);
}
