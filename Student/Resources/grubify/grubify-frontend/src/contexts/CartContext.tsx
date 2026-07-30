import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react';
import {
  AddCartItemRequest,
  Cart,
  UpdateCartItemRequest,
} from '../types';
import { cartService } from '../services/api';

const CART_USER_ID = 'user123';

interface CartContextValue {
  cart: Cart | null;
  itemCount: number;
  refresh: () => Promise<Cart | null>;
  addItem: (item: AddCartItemRequest) => Promise<Cart>;
  updateItem: (itemId: number, item: UpdateCartItemRequest) => Promise<Cart>;
  removeItem: (itemId: number) => Promise<Cart>;
  clear: () => Promise<void>;
}

const CartContext = createContext<CartContextValue | undefined>(undefined);

const countItems = (cart: Cart | null): number =>
  (cart?.items ?? []).reduce((sum, item) => sum + (item.quantity ?? 0), 0);

export const CartProvider: React.FC<{ children: React.ReactNode }> = ({
  children,
}) => {
  const [cart, setCart] = useState<Cart | null>(null);

  const refresh = useCallback(async () => {
    try {
      const data = await cartService.get(CART_USER_ID);
      setCart(data);
      return data;
    } catch {
      return null;
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const addItem = useCallback(async (item: AddCartItemRequest) => {
    const updated = await cartService.addItem(CART_USER_ID, item);
    setCart(updated);
    return updated;
  }, []);

  const updateItem = useCallback(
    async (itemId: number, item: UpdateCartItemRequest) => {
      const updated = await cartService.updateItem(CART_USER_ID, itemId, item);
      setCart(updated);
      return updated;
    },
    [],
  );

  const removeItem = useCallback(async (itemId: number) => {
    const updated = await cartService.removeItem(CART_USER_ID, itemId);
    setCart(updated);
    return updated;
  }, []);

  const clear = useCallback(async () => {
    await cartService.clear(CART_USER_ID);
    setCart((prev) => (prev ? { ...prev, items: [] } : prev));
  }, []);

  const value = useMemo<CartContextValue>(
    () => ({
      cart,
      itemCount: countItems(cart),
      refresh,
      addItem,
      updateItem,
      removeItem,
      clear,
    }),
    [cart, refresh, addItem, updateItem, removeItem, clear],
  );

  return <CartContext.Provider value={value}>{children}</CartContext.Provider>;
};

export const useCart = (): CartContextValue => {
  const ctx = useContext(CartContext);
  if (!ctx) {
    throw new Error('useCart must be used within a CartProvider');
  }
  return ctx;
};
