import React, { useState, useEffect } from 'react';
import {
  Box,
  Typography,
  Container,
  Card,
  CardContent,
  Button,
  IconButton,
  Divider,
  Paper,
  Alert,
  CircularProgress,
} from '@mui/material';
import {
  Add as AddIcon,
  Remove as RemoveIcon,
  Delete as DeleteIcon,
  ShoppingCart as CartIcon,
} from '@mui/icons-material';
import { useNavigate } from 'react-router-dom';
import { Cart, CartItem } from '../types';
import { cartService } from '../services/api';
import { useCart } from '../contexts/CartContext';

const CartPage: React.FC = () => {
  const navigate = useNavigate();
  const { updateItem, removeItem, clear: clearCartContext } = useCart();
  const [cart, setCart] = useState<Cart | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchCart();
  }, []);

  const fetchCart = async () => {
    try {
      setLoading(true);
      const cartData = await cartService.get('user123');
      setCart(cartData);
      setError(null);
    } catch (err) {
      setError('Failed to load cart. Please try again later.');
      console.error('Error fetching cart:', err);
    } finally {
      setLoading(false);
    }
  };

  const updateQuantity = async (itemId: number, newQuantity: number) => {
    if (!cart) return;

    try {
      const updatedCart = await updateItem(itemId, {
        quantity: newQuantity,
        specialInstructions: cart.items.find(item => item.id === itemId)?.specialInstructions || '',
      });
      setCart(updatedCart);
    } catch (err) {
      console.error('Error updating cart item:', err);
    }
  };

  const removeItemFromCart = async (itemId: number) => {
    if (!cart) return;

    try {
      const updatedCart = await removeItem(itemId);
      setCart(updatedCart);
    } catch (err) {
      console.error('Error removing cart item:', err);
    }
  };

  const clearCart = async () => {
    try {
      await clearCartContext();
      setCart(prev => (prev ? { ...prev, items: [] } : prev));
    } catch (err) {
      console.error('Error clearing cart:', err);
    }
  };

  const handleCheckout = () => {
    navigate('/checkout');
  };

  if (loading) {
    return (
      <Box display="flex" justifyContent="center" alignItems="center" minHeight="60vh">
        <CircularProgress size={60} />
      </Box>
    );
  }

  if (error) {
    return (
      <Container maxWidth="md">
        <Alert severity="error" sx={{ mt: 4 }}>
          {error}
        </Alert>
        <Box display="flex" justifyContent="center" mt={2}>
          <Button variant="contained" onClick={fetchCart}>
            Try Again
          </Button>
        </Box>
      </Container>
    );
  }

  if (!cart || cart.items.length === 0) {
    return (
      <Container maxWidth="md">
        <Box textAlign="center" py={8}>
          <CartIcon sx={{ fontSize: 80, color: 'text.secondary', mb: 2 }} />
          <Typography variant="h4" gutterBottom>
            Your cart is empty
          </Typography>
          <Typography variant="body1" color="text.secondary" gutterBottom>
            Add some delicious food to get started!
          </Typography>
          <Button variant="contained" onClick={() => navigate('/')} sx={{ mt: 2 }}>
            Browse Restaurants
          </Button>
        </Box>
      </Container>
    );
  }

  return (
    <Container maxWidth="lg">
      <Typography variant="h3" component="h1" gutterBottom>
        Your Cart
      </Typography>

      <Box sx={{ display: 'flex', gap: 4, flexDirection: { xs: 'column', md: 'row' } }}>
        {/* Cart Items */}
        <Box sx={{ flex: 1 }}>
          <Card>
            <CardContent>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
                <Typography variant="h5">
                  Items ({cart.items.length})
                </Typography>
                <Button
                  color="error"
                  onClick={clearCart}
                  disabled={cart.items.length === 0}
                >
                  Clear Cart
                </Button>
              </Box>

              {cart.items.map((item, index) => (
                <Box key={item.id}>
                  <Box sx={{ display: 'flex', gap: 2, py: 2 }}>
                    <Box
                      component="img"
                      src={item.foodItem.imageUrl}
                      alt={item.foodItem.name}
                      sx={{
                        width: 80,
                        height: 80,
                        objectFit: 'cover',
                        borderRadius: 1,
                      }}
                    />
                    <Box sx={{ flex: 1 }}>
                      <Typography variant="h6" gutterBottom>
                        {item.foodItem.name}
                      </Typography>
                      <Typography variant="body2" color="text.secondary" gutterBottom>
                        {item.foodItem.description}
                      </Typography>
                      {item.specialInstructions && (
                        <Typography variant="body2" sx={{ fontStyle: 'italic', color: 'text.secondary' }}>
                          Note: {item.specialInstructions}
                        </Typography>
                      )}
                      <Typography variant="h6" color="primary" sx={{ mt: 1 }}>
                        ${item.foodItem.price.toFixed(2)}
                      </Typography>
                    </Box>
                    <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 1 }}>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                        <IconButton
                          size="small"
                          onClick={() => updateQuantity(item.id, Math.max(1, item.quantity - 1))}
                        >
                          <RemoveIcon />
                        </IconButton>
                        <Typography variant="h6" sx={{ minWidth: 30, textAlign: 'center' }}>
                          {item.quantity}
                        </Typography>
                        <IconButton
                          size="small"
                          onClick={() => updateQuantity(item.id, item.quantity + 1)}
                        >
                          <AddIcon />
                        </IconButton>
                      </Box>
                      <IconButton
                        color="error"
                        onClick={() => removeItemFromCart(item.id)}
                      >
                        <DeleteIcon />
                      </IconButton>
                      <Typography variant="body2" fontWeight="bold">
                        ${(item.foodItem.price * item.quantity).toFixed(2)}
                      </Typography>
                    </Box>
                  </Box>
                  {index < cart.items.length - 1 && <Divider />}
                </Box>
              ))}
            </CardContent>
          </Card>
        </Box>

        {/* Order Summary */}
        <Box sx={{ width: { xs: '100%', md: 350 } }}>
          <Paper sx={{ p: 3, position: 'sticky', top: 24 }}>
            <Typography variant="h5" gutterBottom>
              Order Summary
            </Typography>
            
            <Box sx={{ space: 2 }}>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                <Typography>Subtotal</Typography>
                <Typography>${cart.subTotal.toFixed(2)}</Typography>
              </Box>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                <Typography>Tax</Typography>
                <Typography>${cart.tax.toFixed(2)}</Typography>
              </Box>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 2 }}>
                <Typography>Delivery Fee</Typography>
                <Typography>${cart.deliveryFee.toFixed(2)}</Typography>
              </Box>
              <Divider sx={{ my: 2 }} />
              <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 3 }}>
                <Typography variant="h6" fontWeight="bold">
                  Total
                </Typography>
                <Typography variant="h6" fontWeight="bold">
                  ${cart.total.toFixed(2)}
                </Typography>
              </Box>
            </Box>

            <Button
              variant="contained"
              fullWidth
              size="large"
              onClick={handleCheckout}
              sx={{ mb: 2 }}
            >
              Proceed to Checkout
            </Button>
            
            <Button
              variant="outlined"
              fullWidth
              onClick={() => navigate('/')}
            >
              Continue Shopping
            </Button>
          </Paper>
        </Box>
      </Box>
    </Container>
  );
};

export default CartPage;
