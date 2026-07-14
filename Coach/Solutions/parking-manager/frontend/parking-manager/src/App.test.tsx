import React from 'react';
import { render, screen } from '@testing-library/react';
import App from './App';

test('renders parking manager title', () => {
  render(<App />);
  const titleElement = screen.getByRole('heading', { name: /Parking Manager/i });
  expect(titleElement).toBeInTheDocument();
});
