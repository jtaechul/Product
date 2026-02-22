const products = [
  {
    id: 1,
    name: 'Standard Cardboard Box (10x10x10)',
    price: 1500,
    image: 'https://placehold.co/200x200?text=Box',
    category: 'Boxes'
  },
  {
    id: 2,
    name: 'Heavy Duty Tape (1 Roll)',
    price: 3000,
    image: 'https://placehold.co/200x200?text=Tape',
    category: 'Tape'
  },
  {
    id: 3,
    name: 'Bubble Wrap (10m)',
    price: 8000,
    image: 'https://placehold.co/200x200?text=Bubble+Wrap',
    category: 'Protection'
  },
  {
    id: 4,
    name: 'Shipping Labels (100 pack)',
    price: 5000,
    image: 'https://placehold.co/200x200?text=Labels',
    category: 'Labels'
  },
  {
    id: 5,
    name: 'Stretch Film',
    price: 12000,
    image: 'https://placehold.co/200x200?text=Stretch+Film',
    category: 'Protection'
  },
  {
    id: 6,
    name: 'Mailers (Padded Envelopes)',
    price: 800,
    image: 'https://placehold.co/200x200?text=Mailers',
    category: 'Envelopes'
  }
];

let cart = [];

function init() {
  renderProducts();
  updateCartUI();
}

function renderProducts() {
  const productContainer = document.getElementById('product-list');
  productContainer.innerHTML = '';

  products.forEach(product => {
    const card = document.createElement('div');
    card.className = 'product-card';
    card.innerHTML = `
      <img src="${product.image}" alt="${product.name}">
      <div class="product-info">
        <h3>${product.name}</h3>
        <p class="price">₩${product.price.toLocaleString()}</p>
        <button onclick="addToCart(${product.id})">Add to Cart</button>
      </div>
    `;
    productContainer.appendChild(card);
  });
}

function addToCart(id) {
  const product = products.find(p => p.id === id);
  const existingItem = cart.find(item => item.id === id);

  if (existingItem) {
    existingItem.quantity += 1;
  } else {
    cart.push({ ...product, quantity: 1 });
  }
  
  updateCartUI();
}

function updateCartUI() {
  const cartItemsContainer = document.getElementById('cart-items');
  const cartTotalElement = document.getElementById('cart-total');
  const cartCountElement = document.getElementById('cart-count');
  
  cartItemsContainer.innerHTML = '';
  
  let total = 0;
  let count = 0;

  cart.forEach(item => {
    total += item.price * item.quantity;
    count += item.quantity;
    
    const li = document.createElement('li');
    li.className = 'cart-item';
    li.innerHTML = `
      <span>${item.name} (x${item.quantity})</span>
      <span>₩${(item.price * item.quantity).toLocaleString()}</span>
    `;
    cartItemsContainer.appendChild(li);
  });

  cartTotalElement.textContent = `₩${total.toLocaleString()}`;
  cartCountElement.textContent = count;
}

window.addToCart = addToCart; // Make accessible globally for onclick
document.addEventListener('DOMContentLoaded', init);
