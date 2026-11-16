import React, { useState, useEffect } from 'react';
import {
  Box,
  Typography,
  Container,
  Card,
  CardContent,
  Paper,
  Stepper,
  Step,
  StepLabel,
  StepContent,
  Chip,
  Button,
  Alert,
  CircularProgress,
  Divider,
} from '@mui/material';
import {
  CheckCircle as CheckCircleIcon,
  RestaurantMenu as RestaurantIcon,
  LocalShipping as DeliveryIcon,
  Home as HomeIcon,
} from '@mui/icons-material';
import { useParams, useNavigate } from 'react-router-dom';
import { Order, OrderStatus } from '../types';
import { orderService } from '../services/api';

const orderSteps = [
  { label: 'Order Placed', icon: <CheckCircleIcon />, status: OrderStatus.Placed },
  { label: 'Order Confirmed', icon: <CheckCircleIcon />, status: OrderStatus.Confirmed },
  { label: 'Preparing Food', icon: <RestaurantIcon />, status: OrderStatus.Preparing },
  { label: 'Out for Delivery', icon: <DeliveryIcon />, status: OrderStatus.OutForDelivery },
  { label: 'Delivered', icon: <HomeIcon />, status: OrderStatus.Delivered },
];

const getStatusColor = (status: OrderStatus) => {
  switch (status) {
    case OrderStatus.Placed:
    case OrderStatus.Confirmed:
      return 'info';
    case OrderStatus.Preparing:
      return 'warning';
    case OrderStatus.OutForDelivery:
      return 'primary';
    case OrderStatus.Delivered:
      return 'success';
    case OrderStatus.Cancelled:
      return 'error';
    default:
      return 'default';
  }
};

const getStatusText = (status: OrderStatus) => {
  switch (status) {
    case OrderStatus.Placed:
      return 'Placed';
    case OrderStatus.Confirmed:
      return 'Confirmed';
    case OrderStatus.Preparing:
      return 'Preparing';
    case OrderStatus.ReadyForPickup:
      return 'Ready for Pickup';
    case OrderStatus.OutForDelivery:
      return 'Out for Delivery';
    case OrderStatus.Delivered:
      return 'Delivered';
    case OrderStatus.Cancelled:
      return 'Cancelled';
    default:
      return 'Unknown';
  }
};

const OrderTrackingPage: React.FC = () => {
  const { orderId } = useParams<{ orderId: string }>();
  const navigate = useNavigate();
  const [order, setOrder] = useState<Order | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (orderId) {
      fetchOrder(parseInt(orderId));
      // Poll for updates every 30 seconds
      const interval = setInterval(() => {
        fetchOrder(parseInt(orderId));
      }, 30000);
      return () => clearInterval(interval);
    }
  }, [orderId]);

  const fetchOrder = async (id: number) => {
    try {
      const orderData = await orderService.getById(id);
      setOrder(orderData);
      setError(null);
    } catch (err) {
      setError('Failed to load order details. Please try again later.');
      console.error('Error fetching order:', err);
    } finally {
      setLoading(false);
    }
  };

  const getCurrentStepIndex = (status: OrderStatus) => {
    return orderSteps.findIndex(step => step.status === status);
  };

  const getEstimatedDeliveryTime = (order: Order) => {
    if (order.status === OrderStatus.Delivered) {
      return `Delivered at ${new Date(order.deliveryTime || order.orderDate).toLocaleTimeString()}`;
    }
    
    const orderDate = new Date(order.orderDate);
    const estimatedTime = new Date(orderDate.getTime() + order.estimatedDeliveryTime * 60000);
    return `Estimated delivery: ${estimatedTime.toLocaleTimeString()}`;
  };

  if (loading) {
    return (
      <Box display="flex" justifyContent="center" alignItems="center" minHeight="60vh">
        <CircularProgress size={60} />
      </Box>
    );
  }

  if (error || !order) {
    return (
      <Container maxWidth="md">
        <Alert severity="error" sx={{ mt: 4 }}>
          {error || 'Order not found'}
        </Alert>
        <Box display="flex" justifyContent="center" mt={2}>
          <Button variant="contained" onClick={() => navigate('/')}>
            Back to Home
          </Button>
        </Box>
      </Container>
    );
  }

  const currentStepIndex = getCurrentStepIndex(order.status);

  return (
    <Container maxWidth="lg">
      <Typography variant="h3" component="h1" gutterBottom>
        Order Tracking
      </Typography>

      <Box sx={{ display: 'flex', gap: 4, flexDirection: { xs: 'column', lg: 'row' } }}>
        {/* Order Status */}
        <Box sx={{ flex: 1 }}>
          <Card sx={{ mb: 4 }}>
            <CardContent>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
                <Typography variant="h5">
                  Order #{order.id}
                </Typography>
                <Chip
                  label={getStatusText(order.status)}
                  color={getStatusColor(order.status)}
                />
              </Box>

              <Typography variant="body1" color="text.secondary" gutterBottom>
                {getEstimatedDeliveryTime(order)}
              </Typography>

              <Stepper activeStep={currentStepIndex} orientation="vertical" sx={{ mt: 3 }}>
                {orderSteps.map((step, index) => (
                  <Step key={step.label}>
                    <StepLabel
                      StepIconComponent={() => (
                        <Box
                          sx={{
                            color: index <= currentStepIndex ? 'primary.main' : 'text.disabled',
                            display: 'flex',
                            alignItems: 'center',
                          }}
                        >
                          {step.icon}
                        </Box>
                      )}
                    >
                      <Typography
                        variant="body1"
                        color={index <= currentStepIndex ? 'primary' : 'text.disabled'}
                      >
                        {step.label}
                      </Typography>
                    </StepLabel>
                    <StepContent>
                      <Typography variant="body2" color="text.secondary">
                        {index === 0 && 'Your order has been placed successfully.'}
                        {index === 1 && 'The restaurant has confirmed your order.'}
                        {index === 2 && 'The restaurant is preparing your food.'}
                        {index === 3 && 'Your food is on the way!'}
                        {index === 4 && 'Your order has been delivered. Enjoy your meal!'}
                      </Typography>
                    </StepContent>
                  </Step>
                ))}
              </Stepper>
            </CardContent>
          </Card>

          {/* Restaurant Info */}
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Restaurant Details
              </Typography>
              <Typography variant="body1" gutterBottom>
                {order.restaurant.name}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                {order.restaurant.address}
              </Typography>
            </CardContent>
          </Card>
        </Box>

        {/* Order Details */}
        <Box sx={{ width: { xs: '100%', lg: 400 } }}>
          {/* Delivery Address */}
          <Paper sx={{ p: 3, mb: 3 }}>
            <Typography variant="h6" gutterBottom>
              Delivery Address
            </Typography>
            <Typography variant="body2">
              {order.deliveryAddress}
            </Typography>
            <Typography variant="body2" sx={{ mt: 1 }}>
              Phone: {order.customerPhone}
            </Typography>
          </Paper>

          {/* Order Items */}
          <Paper sx={{ p: 3, mb: 3 }}>
            <Typography variant="h6" gutterBottom>
              Order Items
            </Typography>
            {order.items.map((item) => (
              <Box key={item.id} sx={{ display: 'flex', gap: 2, mb: 2 }}>
                <Box
                  component="img"
                  src={item.foodItem.imageUrl}
                  alt={item.foodItem.name}
                  sx={{
                    width: 50,
                    height: 50,
                    objectFit: 'cover',
                    borderRadius: 1,
                  }}
                />
                <Box sx={{ flex: 1 }}>
                  <Typography variant="body2" fontWeight="bold">
                    {item.quantity}x {item.foodItem.name}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    ${item.foodItem.price.toFixed(2)} each
                  </Typography>
                  {item.specialInstructions && (
                    <Typography variant="caption" sx={{ fontStyle: 'italic' }}>
                      Note: {item.specialInstructions}
                    </Typography>
                  )}
                </Box>
                <Typography variant="body2" fontWeight="bold">
                  ${(item.foodItem.price * item.quantity).toFixed(2)}
                </Typography>
              </Box>
            ))}
          </Paper>

          {/* Order Summary */}
          <Paper sx={{ p: 3 }}>
            <Typography variant="h6" gutterBottom>
              Order Summary
            </Typography>
            
            <Box sx={{ space: 2 }}>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                <Typography variant="body2">Subtotal</Typography>
                <Typography variant="body2">${order.subTotal.toFixed(2)}</Typography>
              </Box>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                <Typography variant="body2">Tax</Typography>
                <Typography variant="body2">${order.tax.toFixed(2)}</Typography>
              </Box>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 2 }}>
                <Typography variant="body2">Delivery Fee</Typography>
                <Typography variant="body2">${order.deliveryFee.toFixed(2)}</Typography>
              </Box>
              <Divider sx={{ my: 2 }} />
              <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 2 }}>
                <Typography variant="h6" fontWeight="bold">
                  Total
                </Typography>
                <Typography variant="h6" fontWeight="bold">
                  ${order.total.toFixed(2)}
                </Typography>
              </Box>
              <Typography variant="body2" color="text.secondary">
                Paid via {order.paymentMethod}
              </Typography>
            </Box>
          </Paper>

          {/* Actions */}
          <Box sx={{ mt: 3, display: 'flex', gap: 2 }}>
            <Button
              variant="outlined"
              fullWidth
              onClick={() => navigate('/')}
            >
              Order Again
            </Button>
            {order.status !== OrderStatus.Delivered && order.status !== OrderStatus.Cancelled && (
              <Button
                variant="outlined"
                color="error"
                fullWidth
                onClick={() => {
                  // Handle order cancellation
                  console.log('Cancel order');
                }}
              >
                Cancel Order
              </Button>
            )}
          </Box>
        </Box>
      </Box>
    </Container>
  );
};

export default OrderTrackingPage;
