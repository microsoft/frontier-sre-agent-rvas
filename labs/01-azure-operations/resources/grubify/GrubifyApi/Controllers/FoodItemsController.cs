using Microsoft.AspNetCore.Mvc;
using GrubifyApi.Models;

namespace GrubifyApi.Controllers
{
    [ApiController]
    [Route("api/[controller]")]
    public class FoodItemsController : ControllerBase
    {
        private static readonly List<FoodItem> FoodItems = new()
        {
            // Tony's Italian Bistro items
            new FoodItem
            {
                Id = 1,
                Name = "Margherita Pizza",
                Description = "Classic pizza with fresh tomatoes, mozzarella, and basil",
                Price = 16.99m,
                ImageUrl = "/images/food/1.jpg",
                Category = "Pizza",
                IsVegetarian = true,
                IsVegan = false,
                IsSpicy = false,
                RestaurantId = 1,
                PreparationTime = 20
            },
            new FoodItem
            {
                Id = 2,
                Name = "Chicken Alfredo",
                Description = "Creamy fettuccine pasta with grilled chicken and parmesan",
                Price = 19.99m,
                ImageUrl = "/images/food/2.jpg",
                Category = "Pasta",
                IsVegetarian = false,
                IsVegan = false,
                IsSpicy = false,
                RestaurantId = 1,
                PreparationTime = 25
            },
            new FoodItem
            {
                Id = 3,
                Name = "Caesar Salad",
                Description = "Crisp romaine lettuce with caesar dressing and croutons",
                Price = 12.99m,
                ImageUrl = "/images/food/3.jpg",
                Category = "Salad",
                IsVegetarian = true,
                IsVegan = false,
                IsSpicy = false,
                RestaurantId = 1,
                PreparationTime = 10
            },

            // Sakura Sushi items
            new FoodItem
            {
                Id = 4,
                Name = "California Roll",
                Description = "Fresh avocado, cucumber, and crab meat with sesame seeds",
                Price = 14.99m,
                ImageUrl = "/images/food/4.jpg",
                Category = "Sushi",
                IsVegetarian = false,
                IsVegan = false,
                IsSpicy = false,
                RestaurantId = 2,
                PreparationTime = 15
            },
            new FoodItem
            {
                Id = 5,
                Name = "Spicy Tuna Roll",
                Description = "Fresh tuna with spicy mayo and sriracha",
                Price = 16.99m,
                ImageUrl = "/images/food/5.jpg",
                Category = "Sushi",
                IsVegetarian = false,
                IsVegan = false,
                IsSpicy = true,
                RestaurantId = 2,
                PreparationTime = 15
            },
            new FoodItem
            {
                Id = 6,
                Name = "Chicken Teriyaki Bowl",
                Description = "Grilled chicken with teriyaki sauce over steamed rice",
                Price = 18.99m,
                ImageUrl = "/images/food/6.jpg",
                Category = "Bowl",
                IsVegetarian = false,
                IsVegan = false,
                IsSpicy = false,
                RestaurantId = 2,
                PreparationTime = 20
            },

            // Spice Garden items
            new FoodItem
            {
                Id = 7,
                Name = "Chicken Tikka Masala",
                Description = "Tender chicken in a creamy tomato-based curry sauce",
                Price = 17.99m,
                ImageUrl = "/images/food/7.jpg",
                Category = "Curry",
                IsVegetarian = false,
                IsVegan = false,
                IsSpicy = true,
                RestaurantId = 3,
                PreparationTime = 30
            },
            new FoodItem
            {
                Id = 8,
                Name = "Vegetable Biryani",
                Description = "Fragrant basmati rice with mixed vegetables and aromatic spices",
                Price = 15.99m,
                ImageUrl = "/images/food/8.jpg",
                Category = "Rice",
                IsVegetarian = true,
                IsVegan = true,
                IsSpicy = true,
                RestaurantId = 3,
                PreparationTime = 25
            },
            new FoodItem
            {
                Id = 9,
                Name = "Garlic Naan",
                Description = "Fresh baked bread with garlic and herbs",
                Price = 4.99m,
                ImageUrl = "/images/food/9.jpg",
                Category = "Bread",
                IsVegetarian = true,
                IsVegan = false,
                IsSpicy = false,
                RestaurantId = 3,
                PreparationTime = 10
            },

            // Burger Hub items
            new FoodItem
            {
                Id = 10,
                Name = "Classic Cheeseburger",
                Description = "Beef patty with cheese, lettuce, tomato, and special sauce",
                Price = 13.99m,
                ImageUrl = "/images/food/10.jpg",
                Category = "Burger",
                IsVegetarian = false,
                IsVegan = false,
                IsSpicy = false,
                RestaurantId = 4,
                PreparationTime = 15
            },
            new FoodItem
            {
                Id = 11,
                Name = "Crispy Chicken Sandwich",
                Description = "Fried chicken breast with coleslaw and pickles",
                Price = 15.99m,
                ImageUrl = "/images/food/11.jpg",
                Category = "Sandwich",
                IsVegetarian = false,
                IsVegan = false,
                IsSpicy = false,
                RestaurantId = 4,
                PreparationTime = 18
            },
            new FoodItem
            {
                Id = 12,
                Name = "Sweet Potato Fries",
                Description = "Crispy sweet potato fries with sea salt",
                Price = 6.99m,
                ImageUrl = "/images/food/12.jpg",
                Category = "Sides",
                IsVegetarian = true,
                IsVegan = true,
                IsSpicy = false,
                RestaurantId = 4,
                PreparationTime = 12
            },

            // Green Bowl items
            new FoodItem
            {
                Id = 13,
                Name = "Quinoa Buddha Bowl",
                Description = "Quinoa with roasted vegetables, avocado, and tahini dressing",
                Price = 14.99m,
                ImageUrl = "/images/food/13.jpg",
                Category = "Bowl",
                IsVegetarian = true,
                IsVegan = true,
                IsSpicy = false,
                RestaurantId = 5,
                PreparationTime = 15
            },
            new FoodItem
            {
                Id = 14,
                Name = "Acai Berry Smoothie",
                Description = "Acai berries blended with banana and coconut milk",
                Price = 8.99m,
                ImageUrl = "/images/food/14.jpg",
                Category = "Smoothie",
                IsVegetarian = true,
                IsVegan = true,
                IsSpicy = false,
                RestaurantId = 5,
                PreparationTime = 5
            },
            new FoodItem
            {
                Id = 15,
                Name = "Grilled Salmon Salad",
                Description = "Fresh salmon over mixed greens with lemon vinaigrette",
                Price = 18.99m,
                ImageUrl = "/images/food/15.jpg",
                Category = "Salad",
                IsVegetarian = false,
                IsVegan = false,
                IsSpicy = false,
                RestaurantId = 5,
                PreparationTime = 20
            }
        };

        [HttpGet]
        public ActionResult<IEnumerable<FoodItem>> GetFoodItems()
        {
            return Ok(FoodItems);
        }

        [HttpGet("{id}")]
        public ActionResult<FoodItem> GetFoodItem(int id)
        {
            var foodItem = FoodItems.FirstOrDefault(f => f.Id == id);
            if (foodItem == null)
            {
                return NotFound();
            }
            return Ok(foodItem);
        }

        [HttpGet("restaurant/{restaurantId}")]
        public ActionResult<IEnumerable<FoodItem>> GetFoodItemsByRestaurant(int restaurantId)
        {
            var items = FoodItems.Where(f => f.RestaurantId == restaurantId).ToList();
            return Ok(items);
        }

        [HttpGet("category/{category}")]
        public ActionResult<IEnumerable<FoodItem>> GetFoodItemsByCategory(string category)
        {
            var items = FoodItems.Where(f => 
                f.Category.Equals(category, StringComparison.OrdinalIgnoreCase)).ToList();
            return Ok(items);
        }

        [HttpGet("search")]
        public ActionResult<IEnumerable<FoodItem>> SearchFoodItems([FromQuery] string query)
        {
            if (string.IsNullOrEmpty(query))
            {
                return Ok(FoodItems);
            }

            var items = FoodItems.Where(f => 
                f.Name.Contains(query, StringComparison.OrdinalIgnoreCase) ||
                f.Description.Contains(query, StringComparison.OrdinalIgnoreCase) ||
                f.Category.Contains(query, StringComparison.OrdinalIgnoreCase)).ToList();
            
            return Ok(items);
        }

        [HttpGet("dietary")]
        public ActionResult<IEnumerable<FoodItem>> GetFoodItemsByDietaryPreference(
            [FromQuery] bool? isVegetarian = null,
            [FromQuery] bool? isVegan = null,
            [FromQuery] bool? isSpicy = null)
        {
            var items = FoodItems.AsQueryable();

            if (isVegetarian.HasValue)
                items = items.Where(f => f.IsVegetarian == isVegetarian.Value);

            if (isVegan.HasValue)
                items = items.Where(f => f.IsVegan == isVegan.Value);

            if (isSpicy.HasValue)
                items = items.Where(f => f.IsSpicy == isSpicy.Value);

            return Ok(items.ToList());
        }
    }
}
