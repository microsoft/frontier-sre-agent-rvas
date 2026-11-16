namespace GrubifyApi.Models
{
    public enum OrderStatus
    {
        Placed = 1,
        Confirmed = 2,
        Preparing = 3,
        ReadyForPickup = 4,
        OutForDelivery = 5,
        Delivered = 6,
        Cancelled = 7
    }

    public class Order
    {
        public int Id { get; set; }
        public string UserId { get; set; } = string.Empty;
        public int RestaurantId { get; set; }
        public Restaurant Restaurant { get; set; } = new Restaurant();
        public List<CartItem> Items { get; set; } = new List<CartItem>();
        public decimal SubTotal { get; set; }
        public decimal Tax { get; set; }
        public decimal DeliveryFee { get; set; }
        public decimal Total { get; set; }
        public OrderStatus Status { get; set; } = OrderStatus.Placed;
        public DateTime OrderDate { get; set; } = DateTime.UtcNow;
        public DateTime? DeliveredDate { get; set; }
        public DateTime? DeliveryTime { get; set; }
        public string DeliveryAddress { get; set; } = string.Empty;
        public string CustomerName { get; set; } = string.Empty;
        public string CustomerPhone { get; set; } = string.Empty;
        public string PaymentMethod { get; set; } = string.Empty;
        public string SpecialInstructions { get; set; } = string.Empty;
        public int EstimatedDeliveryTime { get; set; } // in minutes
    }
}
