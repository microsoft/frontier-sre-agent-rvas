export interface Restaurant {
  id: number;
  name: string;
  description: string;
  imageUrl: string;
  cuisineType: string;
  rating: number;
  deliveryTime: string;
  deliveryFee: number;
  minimumOrder: number;
  isOpen: boolean;
  address: string;
}

export interface FoodItem {
  id: number;
  name: string;
  description: string;
  price: number;
  imageUrl: string;
  category: string;
  isVegetarian: boolean;
  isVegan: boolean;
  isSpicy: boolean;
  restaurantId: number;
  isAvailable: boolean;
  preparationTime: number;
}

export interface CartItem {
  id: number;
  foodItemId: number;
  foodItem: FoodItem;
  quantity: number;
  specialInstructions: string;
}

export interface Cart {
  id: number;
  userId: string;
  items: CartItem[];
  subTotal: number;
  tax: number;
  deliveryFee: number;
  total: number;
}

export enum OrderStatus {
  Placed = 1,
  Confirmed = 2,
  Preparing = 3,
  ReadyForPickup = 4,
  OutForDelivery = 5,
  Delivered = 6,
  Cancelled = 7
}

export interface Order {
  id: number;
  userId: string;
  restaurantId: number;
  restaurant: Restaurant;
  items: CartItem[];
  subTotal: number;
  tax: number;
  deliveryFee: number;
  total: number;
  status: OrderStatus;
  orderDate: string;
  deliveredDate?: string;
  deliveryTime?: string;
  deliveryAddress: string;
  customerName: string;
  customerPhone: string;
  paymentMethod: string;
  specialInstructions: string;
  estimatedDeliveryTime: number;
}

export interface AddCartItemRequest {
  foodItemId: number;
  quantity: number;
  specialInstructions: string;
}

export interface UpdateCartItemRequest {
  quantity: number;
  specialInstructions: string;
}

export interface PlaceOrderRequest {
  userId: string;
  restaurantId: number;
  items: CartItem[];
  deliveryAddress: string;
  paymentMethod: string;
  specialInstructions: string;
}
