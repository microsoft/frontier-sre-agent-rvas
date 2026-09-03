<!-- Use this file to provide workspace-specific custom instructions to Copilot. For more details, visit https://code.visualstudio.com/docs/copilot/copilot-customization#_use-a-githubcopilotinstructionsmd-file -->

# Grubify Food Delivery App

This is a food delivery application with a React TypeScript frontend and .NET backend. Its source
is retained for Azure SRE Agent investigation and remediation exercises.

## Tech Stack
- **Frontend**: React 18 with TypeScript, Material-UI, React Router
- **Backend**: .NET 9 Web API with Controllers
- **Runtime**: Azure Container Apps provisioned by the workshop Terraform root
- **Images**: canonical public `grubify-api:latest` and `grubify-frontend:latest` packages

## Architecture
- Clean separation between frontend and backend
- RESTful API design
- Responsive Material-UI components
- Terraform owns runtime image references, environment variables, and replica settings

## Development Guidelines
- Use TypeScript strict mode
- Follow Material-UI design patterns
- Implement proper error handling
- Use async/await for API calls
- Follow RESTful conventions for API endpoints

## API Endpoints
- `/api/restaurants` - Restaurant management
- `/api/fooditems` - Food item management  
- `/api/cart` - Shopping cart operations
- `/api/orders` - Order management

## UI Components
- Modern, responsive design inspired by popular food delivery apps
- Card-based layouts for restaurants and food items
- Step-by-step checkout process
- Real-time order tracking

Source changes end at a reviewed pull request. Do not add deployment automation, Bicep/AZD
infrastructure, registry credentials, or out-of-band Azure Container App updates. Prioritize user
experience, maintain clean code architecture, and ensure proper error handling throughout the
application.
