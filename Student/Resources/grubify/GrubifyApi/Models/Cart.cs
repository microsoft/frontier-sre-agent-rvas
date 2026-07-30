namespace GrubifyApi.Models
{
    public class CartItem
    {
        public int Id { get; set; }
        public int FoodItemId { get; set; }
        public FoodItem FoodItem { get; set; } = new FoodItem();
        public int Quantity { get; set; }
        public string SpecialInstructions { get; set; } = string.Empty;
    }

    public class Cart
    {
        public int Id { get; set; }
        public string UserId { get; set; } = string.Empty;
        public List<CartItem> Items { get; set; } = new List<CartItem>();
        public decimal SubTotal => Items.Sum(item => item.FoodItem.Price * item.Quantity);
        public decimal Tax => SubTotal * 0.08m; // 8% tax
        public decimal DeliveryFee { get; set; } = 2.99m;
        public decimal Total => SubTotal + Tax + DeliveryFee;
    }
}
