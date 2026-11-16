namespace GrubifyApi.Models
{
    public class Restaurant
    {
        public int Id { get; set; }
        public string Name { get; set; } = string.Empty;
        public string Description { get; set; } = string.Empty;
        public string ImageUrl { get; set; } = string.Empty;
        public double Rating { get; set; }
        public string Address { get; set; } = string.Empty;
        public string CuisineType { get; set; } = string.Empty;
        public string DeliveryTime { get; set; } = string.Empty; // e.g., "25-40 min"
        public decimal DeliveryFee { get; set; }
        public decimal MinimumOrder { get; set; }
        public bool IsOpen { get; set; }
        public List<FoodItem> MenuItems { get; set; } = new List<FoodItem>();
    }
}
