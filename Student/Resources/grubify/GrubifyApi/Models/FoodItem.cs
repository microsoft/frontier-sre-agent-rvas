namespace GrubifyApi.Models
{
    public class FoodItem
    {
        public int Id { get; set; }
        public string Name { get; set; } = string.Empty;
        public string Description { get; set; } = string.Empty;
        public decimal Price { get; set; }
        public string ImageUrl { get; set; } = string.Empty;
        public string Category { get; set; } = string.Empty;
        public bool IsVegetarian { get; set; }
        public bool IsVegan { get; set; }
        public bool IsSpicy { get; set; }
        public int RestaurantId { get; set; }
        public bool IsAvailable { get; set; } = true;
        public int PreparationTime { get; set; } // in minutes
    }
}
