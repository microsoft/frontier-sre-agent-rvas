using Microsoft.AspNetCore.Mvc;
using GrubifyApi.Models;

namespace GrubifyApi.Controllers
{
    [ApiController]
    [Route("api/[controller]")]
    public class OrdersController : ControllerBase
    {
        // In-memory order storage (in production, use database)
        private static readonly List<Order> Orders = new();
        private static int NextOrderId = 1;
        
        // Version detection based on environment or Docker image tag
        private readonly bool _isV2Version;
        
        public OrdersController()
        {
            // Detect version from environment variable (set in Docker builds)
            var version = Environment.GetEnvironmentVariable("API_VERSION") ?? "v1";
            _isV2Version = version.ToLower() == "v2";
            
            Console.WriteLine($"OrdersController initialized with version: {version}");
        }

        private PaymentResult ProcessPayment(string paymentMethod)
        {
            if (_isV2Version)
            {
                // V2: BUG - Payment gateway configuration is incorrect in production
                // This was supposed to be fixed in the last deployment but got missed
                var gatewayUrl = GetPaymentGatewayUrlV2();
                
                Console.WriteLine($"V2: Attempting payment processing with gateway: {gatewayUrl}");
                
                // Connection always fails due to wrong endpoint
                return new PaymentResult 
                { 
                    Success = false, 
                    ErrorMessage = "Connection to payment gateway timed out" 
                };
            }
            else
            {
                // V1: Working payment processing
                var gatewayUrl = GetPaymentGatewayUrlV1();
                
                Console.WriteLine($"V1: Processing payment successfully with gateway: {gatewayUrl}");
                
                // Simulate successful payment processing
                return new PaymentResult 
                { 
                    Success = true, 
                    ErrorMessage = string.Empty 
                };
            }
        }

        private string GetPaymentGatewayUrlV1()
        {
            // V1: Correct production payment gateway URL
            return "https://payment-gateway-prod.grubify.com/v1/process";
        }
        
        private string GetPaymentGatewayUrlV2()
        {
            // V2: Wrong URL that doesn't exist (bug introduced in v2)
            return "https://payment-gateway-staging.internal.com/v1/process";
        }

        [HttpPost]
        public ActionResult<Order> PlaceOrder([FromBody] PlaceOrderRequest request)
        {
            Console.WriteLine($"PlaceOrder called - Version: {(_isV2Version ? "v2" : "v1")}");
            
            // Validate payment information
            if (string.IsNullOrEmpty(request.PaymentMethod))
            {
                return BadRequest("Payment method is required");
            }

            // Process payment through gateway
            var paymentResult = ProcessPayment(request.PaymentMethod);
            if (!paymentResult.Success)
            {
                Console.WriteLine($"Payment processing failed in {(_isV2Version ? "v2" : "v1")}: {paymentResult.ErrorMessage}");
                return StatusCode(500, new { 
                    error = "Payment processing failed",
                    code = "PAYMENT_ERROR",
                    message = "Unable to process payment. Please check your payment information and try again.",
                    timestamp = DateTime.UtcNow,
                    details = paymentResult.ErrorMessage,
                    version = _isV2Version ? "v2" : "v1"
                });
            }

            // V1 reaches here (successful payment), V2 never reaches here
            Console.WriteLine($"Payment successful in {(_isV2Version ? "v2" : "v1")} - creating order");
            var order = new Order
            {
                Id = NextOrderId++,
                UserId = request.UserId,
                RestaurantId = request.RestaurantId,
                Items = request.Items.Select(item => new CartItem
                {
                    Id = item.Id,
                    FoodItemId = item.FoodItemId,
                    FoodItem = item.FoodItem,
                    Quantity = item.Quantity,
                    SpecialInstructions = item.SpecialInstructions
                }).ToList(),
                Status = OrderStatus.Placed,
                OrderDate = DateTime.UtcNow,
                DeliveryAddress = request.DeliveryAddress,
                PaymentMethod = request.PaymentMethod,
                SpecialInstructions = request.SpecialInstructions
            };

            Orders.Add(order);

            // Simulate order status updates after placement
            Task.Run(async () =>
            {
                await Task.Delay(30000); // 30 seconds
                order.Status = OrderStatus.Confirmed;
                
                await Task.Delay(600000); // 10 minutes
                order.Status = OrderStatus.Preparing;
                
                await Task.Delay(900000); // 15 minutes
                order.Status = OrderStatus.OutForDelivery;
                
                await Task.Delay(600000); // 10 minutes
                order.Status = OrderStatus.Delivered;
                order.DeliveryTime = DateTime.UtcNow;
            });

            return CreatedAtAction(nameof(GetOrder), new { id = order.Id }, order);
        }

        [HttpGet("{id}")]
        public ActionResult<Order> GetOrder(int id)
        {
            var order = Orders.FirstOrDefault(o => o.Id == id);
            if (order == null)
            {
                return NotFound();
            }
            return Ok(order);
        }

        [HttpGet("user/{userId}")]
        public ActionResult<IEnumerable<Order>> GetUserOrders(string userId)
        {
            var userOrders = Orders.Where(o => o.UserId == userId)
                                 .OrderByDescending(o => o.OrderDate)
                                 .ToList();
            return Ok(userOrders);
        }

        [HttpGet("user/{userId}/active")]
        public ActionResult<IEnumerable<Order>> GetActiveUserOrders(string userId)
        {
            var activeOrders = Orders.Where(o => o.UserId == userId && 
                                          o.Status != OrderStatus.Delivered && 
                                          o.Status != OrderStatus.Cancelled)
                                   .OrderByDescending(o => o.OrderDate)
                                   .ToList();
            return Ok(activeOrders);
        }

        [HttpPut("{id}/cancel")]
        public ActionResult<Order> CancelOrder(int id)
        {
            var order = Orders.FirstOrDefault(o => o.Id == id);
            if (order == null)
            {
                return NotFound();
            }

            if (order.Status == OrderStatus.Preparing || 
                order.Status == OrderStatus.OutForDelivery)
            {
                return BadRequest("Cannot cancel order that is already being prepared or delivered");
            }

            order.Status = OrderStatus.Cancelled;
            return Ok(order);
        }

        [HttpGet("restaurant/{restaurantId}")]
        public ActionResult<IEnumerable<Order>> GetRestaurantOrders(int restaurantId)
        {
            var restaurantOrders = Orders.Where(o => o.RestaurantId == restaurantId)
                                       .OrderByDescending(o => o.OrderDate)
                                       .ToList();
            return Ok(restaurantOrders);
        }

        [HttpPut("{id}/status")]
        public ActionResult<Order> UpdateOrderStatus(int id, [FromBody] UpdateOrderStatusRequest request)
        {
            var order = Orders.FirstOrDefault(o => o.Id == id);
            if (order == null)
            {
                return NotFound();
            }

            order.Status = request.Status;
            if (request.Status == OrderStatus.Delivered)
            {
                order.DeliveryTime = DateTime.UtcNow;
            }

            return Ok(order);
        }
    }

    public class PlaceOrderRequest
    {
        public string UserId { get; set; } = string.Empty;
        public int RestaurantId { get; set; }
        public List<CartItem> Items { get; set; } = new();
        public string DeliveryAddress { get; set; } = string.Empty;
        public string PaymentMethod { get; set; } = string.Empty;
        public string SpecialInstructions { get; set; } = string.Empty;
    }

    public class UpdateOrderStatusRequest
    {
        public OrderStatus Status { get; set; }
    }

    public class PaymentResult
    {
        public bool Success { get; set; }
        public string ErrorMessage { get; set; } = string.Empty;
    }
}
