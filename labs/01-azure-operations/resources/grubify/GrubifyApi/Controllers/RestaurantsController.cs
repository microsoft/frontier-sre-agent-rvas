using Microsoft.AspNetCore.Mvc;
using GrubifyApi.Models;

namespace GrubifyApi.Controllers
{
    [ApiController]
    [Route("api/[controller]")]
    public class RestaurantsController : ControllerBase
    {
        private static readonly List<Restaurant> Restaurants = new()
        {
            new Restaurant
            {
                Id = 1,
                Name = "Tony's Italian Bistro",
                Description = "Authentic Italian cuisine with fresh ingredients and traditional recipes",
                ImageUrl = "/images/restaurants/1.jpg",
                CuisineType = "Italian",
                Rating = 4.8,
                DeliveryTime = "25-40 min",
                DeliveryFee = 2.99m,
                MinimumOrder = 15.00m,
                IsOpen = true,
                Address = "123 Main St, Downtown"
            },
            new Restaurant
            {
                Id = 2,
                Name = "Sakura Sushi",
                Description = "Fresh sushi and Japanese dishes made by expert chefs",
                ImageUrl = "/images/restaurants/2.jpg",
                CuisineType = "Japanese",
                Rating = 4.7,
                DeliveryTime = "30-45 min",
                DeliveryFee = 3.99m,
                MinimumOrder = 20.00m,
                IsOpen = true,
                Address = "456 Oak Ave, Midtown"
            },
            new Restaurant
            {
                Id = 3,
                Name = "Spice Garden",
                Description = "Flavorful Indian curries and tandoor specialties",
                ImageUrl = "/images/restaurants/3.jpg",
                CuisineType = "Indian",
                Rating = 4.6,
                DeliveryTime = "35-50 min",
                DeliveryFee = 2.49m,
                MinimumOrder = 18.00m,
                IsOpen = true,
                Address = "789 Spice Lane, Eastside"
            },
            new Restaurant
            {
                Id = 4,
                Name = "Burger Hub",
                Description = "Gourmet burgers and crispy fries made to perfection",
                ImageUrl = "/images/restaurants/4.jpg",
                CuisineType = "American",
                Rating = 4.5,
                DeliveryTime = "20-35 min",
                DeliveryFee = 1.99m,
                MinimumOrder = 12.00m,
                IsOpen = true,
                Address = "321 Burger Blvd, Westside"
            },
            new Restaurant
            {
                Id = 5,
                Name = "Green Bowl",
                Description = "Healthy bowls, salads, and smoothies for a balanced lifestyle",
                ImageUrl = "/images/restaurants/5.jpg",
                CuisineType = "Healthy",
                Rating = 4.4,
                DeliveryTime = "15-30 min",
                DeliveryFee = 2.99m,
                MinimumOrder = 10.00m,
                IsOpen = true,
                Address = "654 Health St, Northside"
            }
        };

        [HttpGet]
        public ActionResult<IEnumerable<Restaurant>> GetRestaurants()
        {
            return Ok(Restaurants);
        }

        [HttpGet("{id}")]
        public ActionResult<Restaurant> GetRestaurant(int id)
        {
            var restaurant = Restaurants.FirstOrDefault(r => r.Id == id);
            if (restaurant == null)
            {
                return NotFound();
            }
            return Ok(restaurant);
        }

        [HttpGet("cuisine/{cuisineType}")]
        public ActionResult<IEnumerable<Restaurant>> GetRestaurantsByCuisine(string cuisineType)
        {
            var restaurants = Restaurants.Where(r => 
                r.CuisineType.Equals(cuisineType, StringComparison.OrdinalIgnoreCase)).ToList();
            return Ok(restaurants);
        }

        [HttpGet("search")]
        public ActionResult<IEnumerable<Restaurant>> SearchRestaurants([FromQuery] string query)
        {
            if (string.IsNullOrEmpty(query))
            {
                return Ok(Restaurants);
            }

            var restaurants = Restaurants.Where(r => 
                r.Name.Contains(query, StringComparison.OrdinalIgnoreCase) ||
                r.CuisineType.Contains(query, StringComparison.OrdinalIgnoreCase) ||
                r.Description.Contains(query, StringComparison.OrdinalIgnoreCase)).ToList();
            
            return Ok(restaurants);
        }
    }
}
