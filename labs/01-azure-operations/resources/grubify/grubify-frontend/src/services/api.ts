import axios from 'axios';
import {
  Restaurant,
  FoodItem,
  Cart,
  Order,
  AddCartItemRequest,
  UpdateCartItemRequest,
  PlaceOrderRequest
} from '../types';

const API_BASE_URL = process.env.REACT_APP_API_BASE_URL || 'http://localhost:5291/api';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

export const restaurantService = {
  getAll: (): Promise<Restaurant[]> => 
    api.get('/restaurants').then(response => response.data),
  
  getById: (id: number): Promise<Restaurant> => 
    api.get(`/restaurants/${id}`).then(response => response.data),
  
  getByCuisine: (cuisineType: string): Promise<Restaurant[]> => 
    api.get(`/restaurants/cuisine/${cuisineType}`).then(response => response.data),
  
  search: (query: string): Promise<Restaurant[]> => 
    api.get(`/restaurants/search?query=${query}`).then(response => response.data),
};

export const foodItemService = {
  getAll: (): Promise<FoodItem[]> => 
    api.get('/fooditems').then(response => response.data),
  
  getById: (id: number): Promise<FoodItem> => 
    api.get(`/fooditems/${id}`).then(response => response.data),
  
  getByRestaurant: (restaurantId: number): Promise<FoodItem[]> => 
    api.get(`/fooditems/restaurant/${restaurantId}`).then(response => response.data),
  
  getByCategory: (category: string): Promise<FoodItem[]> => 
    api.get(`/fooditems/category/${category}`).then(response => response.data),
  
  search: (query: string): Promise<FoodItem[]> => 
    api.get(`/fooditems/search?query=${query}`).then(response => response.data),
  
  getByDietaryPreference: (isVegetarian?: boolean, isVegan?: boolean, isSpicy?: boolean): Promise<FoodItem[]> => {
    const params = new URLSearchParams();
    if (isVegetarian !== undefined) params.append('isVegetarian', isVegetarian.toString());
    if (isVegan !== undefined) params.append('isVegan', isVegan.toString());
    if (isSpicy !== undefined) params.append('isSpicy', isSpicy.toString());
    return api.get(`/fooditems/dietary?${params.toString()}`).then(response => response.data);
  },
};

export const cartService = {
  get: (userId: string): Promise<Cart> => 
    api.get(`/cart/${userId}`).then(response => response.data),
  
  addItem: (userId: string, item: AddCartItemRequest): Promise<Cart> => 
    api.post(`/cart/${userId}/items`, item).then(response => response.data),
  
  updateItem: (userId: string, itemId: number, item: UpdateCartItemRequest): Promise<Cart> => 
    api.put(`/cart/${userId}/items/${itemId}`, item).then(response => response.data),
  
  removeItem: (userId: string, itemId: number): Promise<Cart> => 
    api.delete(`/cart/${userId}/items/${itemId}`).then(response => response.data),
  
  clear: (userId: string): Promise<void> => 
    api.delete(`/cart/${userId}`).then(response => response.data),
};

export const orderService = {
  place: (order: PlaceOrderRequest): Promise<Order> => 
    api.post('/orders', order).then(response => response.data),
  
  getById: (id: number): Promise<Order> => 
    api.get(`/orders/${id}`).then(response => response.data),
  
  getByUser: (userId: string): Promise<Order[]> => 
    api.get(`/orders/user/${userId}`).then(response => response.data),
  
  getActiveByUser: (userId: string): Promise<Order[]> => 
    api.get(`/orders/user/${userId}/active`).then(response => response.data),
  
  cancel: (id: number): Promise<Order> => 
    api.put(`/orders/${id}/cancel`).then(response => response.data),
};
