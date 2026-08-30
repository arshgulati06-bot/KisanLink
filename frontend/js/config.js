/**
 * KisanLink - Frontend Configuration & Prototype State Store
 * SIH 2026 — PS SIH26132: Market Linkages & Price Discovery
 * Centralized settings, REST routes, and prototype datasets
 */

const CONFIG = {
  // Application Metadata
  APP_NAME: 'KisanLink',
  PS_CODE: 'SIH26132',
  THEME: 'Agriculture, FoodTech & Rural Development',
  VERSION: '1.2.0-step2',
  IS_PROTOTYPE: true,

  // Backend API Base URL (Configurable for local vs production environments)
  API_BASE_URL: window.KISANLINK_API_URL || 'http://localhost:5000/api',

  // Request Timeout in milliseconds
  REQUEST_TIMEOUT_MS: 8000,

  // REST API Endpoints according to Master Architecture Spec
  ENDPOINTS: {
    AUTH: {
      REGISTER: '/auth/register',
      LOGIN: '/auth/login',
      LOGOUT: '/auth/logout',
      ME: '/auth/me'
    },
    FARMER: {
      PROFILE: '/farmers/profile',
      LOTS: '/lots',
      LOT_DETAIL: (lotId) => `/lots/${lotId}`
    },
    BUYER: {
      PROFILE: '/buyers/profile',
      DEMANDS: '/buyer-demands',
      DEMAND_DETAIL: (demandId) => `/buyer-demands/${demandId}`
    },
    MARKET: {
      LIST: '/markets',
      PRICES: '/prices',
      TRENDS: '/prices/trends',
      ARRIVALS: '/markets/arrivals'
    },
    INTELLIGENCE: {
      MATCHING: '/matching',
      RECOMMENDATION: '/recommendations',
      SALE_WINDOW: '/recommendations/sale-window'
    },
    OFFERS: {
      LIST: '/offers',
      CREATE: '/offers',
      ACCEPT: (offerId) => `/offers/${offerId}/accept`,
      REJECT: (offerId) => `/offers/${offerId}/reject`
    },
    TRANSACTIONS: {
      LIST: '/transactions',
      DETAIL: (txId) => `/transactions/${txId}`
    },
    GRIEVANCE: {
      SUBMIT: '/grievances',
      STATUS: (ticketId) => `/grievances/${ticketId}`
    }
  },

  // Prototype Initial Seed Data (Demo Datasets)
  INITIAL_DATA: {
    FARMER_PROFILE: {
      id: 'FARMER_001',
      name: 'Ramesh Patil',
      type: 'Individual Farmer / Producer',
      location: 'Dindori Taluka, Nashik District, Maharashtra',
      apmcZone: 'Nashik APMC',
      landHolding: '4.5 Acres',
      phone: '+91 98220 XXXXX',
      verified: true
    },

    BUYER_PROFILE: {
      id: 'BUYER_001',
      name: 'Sahyadri Agro Processors Ltd.',
      type: 'Food Processor',
      location: 'Sanaswadi Industrial Zone, Pune, Maharashtra',
      procurementZone: 'Western Maharashtra Hub',
      contactPerson: 'Vikram Joshi (Procurement Head)',
      phone: '+91 98450 XXXXX',
      trustStatus: 'Platform-Reviewed Processor',
      reliabilityScore: '95%'
    },

    LOTS: [
      {
        id: 'LOT-2026-081',
        crop: 'Onion (कांदा)',
        variety: 'Garwa / Red Onion',
        quantity: 10,
        unit: 'QTL',
        grade: 'Grade A',
        location: 'Dindori, Nashik (Maharashtra)',
        harvestDate: '2026-08-25',
        expectedPrice: 3200,
        status: 'OFFER_RECEIVED',
        createdDate: '2026-08-28'
      },
      {
        id: 'LOT-2026-082',
        crop: 'Tomato (टोमॅटो)',
        variety: 'Abhinav Hybrid',
        quantity: 15,
        unit: 'QTL',
        grade: 'Grade A',
        location: 'Narayangaon Belt, Pune District',
        harvestDate: '2026-08-29',
        expectedPrice: 2650,
        status: 'ACTIVE_MARKET',
        createdDate: '2026-08-29'
      }
    ],

    BUYER_DEMANDS: [
      {
        id: 'DEMAND-2026-101',
        buyerName: 'Sahyadri Agro Processors',
        buyerType: 'Food Processor',
        crop: 'Onion (कांदा)',
        quantity: 50,
        unit: 'QTL',
        grade: 'Grade A',
        deliveryLocation: 'Pune Processing Plant',
        offeredRate: 3200,
        requiredDate: '2026-09-05',
        status: 'ACTIVE'
      },
      {
        id: 'DEMAND-2026-102',
        buyerName: 'MahaFresh Institutional',
        buyerType: 'Institutional Procurement',
        crop: 'Tomato (टोमॅटो)',
        quantity: 40,
        unit: 'QTL',
        grade: 'Grade A or B',
        deliveryLocation: 'Navi Mumbai Hub',
        offeredRate: 2650,
        requiredDate: '2026-09-02',
        status: 'ACTIVE'
      }
    ],

    OFFERS: [
      {
        id: 'OFFER-7701',
        lotId: 'LOT-2026-081',
        crop: 'Onion (Grade A)',
        buyerName: 'Sahyadri Agro Processors Ltd.',
        buyerType: 'Food Processor',
        buyerLocation: 'Pune (38 km)',
        offeredRate: 3200,
        quantity: 10,
        unit: 'QTL',
        transportProvided: false,
        estimatedTransportCost: 100,
        netTakeHome: 3220,
        status: 'PENDING',
        terms: 'Payment via Direct RTGS within 24 hours of delivery. Farm pickup available on request.',
        receivedDate: '2026-08-29 14:30'
      }
    ],

    TRANSACTIONS: [
      {
        id: 'TX-2026-044',
        lotId: 'LOT-2026-070',
        crop: 'Soybean (Standard Yellow)',
        quantity: 20,
        unit: 'QTL',
        buyerName: 'Deccan Agri Aggregators',
        agreedRate: 4850,
        grossTotal: 97000,
        status: 'LOGISTICS_PENDING',
        currentStep: 3, // 1: Offered, 2: Accepted, 3: Logistics, 4: Delivered, 5: Paid
        date: '2026-08-27'
      }
    ]
  },

  // Market Intelligence Demonstration Data
  DEMO_DATA: {
    COMMODITIES: {
      Onion: {
        crop: 'Onion (कांदा)',
        grade: 'Grade A',
        lotSize: '1,000 kg (10 QTL)',
        modalPriceAvg: '₹3,050',
        markets: [
          {
            market: 'Pune APMC (Gultekdi)',
            type: 'Primary APMC',
            currentPrice: 3200,
            expectedPrice: 3350,
            trend: 'Rising (+4.7%)',
            demand: 'High',
            arrival: '1,420 MT',
            distance: '38 km',
            transportCost: 100,
            storageCost: 30,
            netRealisation: 3220,
            isRecommended: true
          },
          {
            market: 'Lasalgaon APMC',
            type: 'Major Hub',
            currentPrice: 3100,
            expectedPrice: 3150,
            trend: 'Stable (+1.6%)',
            demand: 'Very High',
            arrival: '3,850 MT',
            distance: '145 km',
            transportCost: 280,
            storageCost: 30,
            netRealisation: 2840,
            isRecommended: false
          },
          {
            market: 'Nashik APMC',
            type: 'Regional APMC',
            currentPrice: 3050,
            expectedPrice: 3100,
            trend: 'Stable (+1.6%)',
            demand: 'Moderate',
            arrival: '1,890 MT',
            distance: '110 km',
            transportCost: 210,
            storageCost: 30,
            netRealisation: 2860,
            isRecommended: false
          },
          {
            market: 'Vashi APMC (Mumbai)',
            type: 'Terminal Market',
            currentPrice: 3450,
            expectedPrice: 3400,
            trend: 'Slight Dip (-1.4%)',
            demand: 'High',
            arrival: '2,600 MT',
            distance: '165 km',
            transportCost: 340,
            storageCost: 40,
            netRealisation: 3020,
            isRecommended: false
          }
        ]
      },
      Tomato: {
        crop: 'Tomato (टोमॅटो)',
        grade: 'Grade A',
        lotSize: '1,500 kg (15 QTL)',
        modalPriceAvg: '₹2,400',
        markets: [
          {
            market: 'Narayangaon APMC',
            type: 'Specialized Tomato Market',
            currentPrice: 2650,
            expectedPrice: 2750,
            trend: 'Rising (+3.8%)',
            demand: 'Very High',
            arrival: '2,100 MT',
            distance: '45 km',
            transportCost: 90,
            storageCost: 20,
            netRealisation: 2640,
            isRecommended: true
          },
          {
            market: 'Pune APMC',
            type: 'Primary APMC',
            currentPrice: 2500,
            expectedPrice: 2520,
            trend: 'Stable (+0.8%)',
            demand: 'High',
            arrival: '1,750 MT',
            distance: '55 km',
            transportCost: 120,
            storageCost: 20,
            netRealisation: 2380,
            isRecommended: false
          },
          {
            market: 'Sangamner APMC',
            type: 'Regional APMC',
            currentPrice: 2350,
            expectedPrice: 2300,
            trend: 'Bearish (-2.1%)',
            demand: 'Moderate',
            arrival: '980 MT',
            distance: '85 km',
            transportCost: 170,
            storageCost: 20,
            netRealisation: 2110,
            isRecommended: false
          }
        ]
      },
      Soybean: {
        crop: 'Soybean (सोयाबीन)',
        grade: 'Standard Yellow',
        lotSize: '2,500 kg (25 QTL)',
        modalPriceAvg: '₹4,600',
        markets: [
          {
            market: 'Latur APMC',
            type: 'Major Oilseed Hub',
            currentPrice: 4850,
            expectedPrice: 4950,
            trend: 'Rising (+2.0%)',
            demand: 'High',
            arrival: '4,200 MT',
            distance: '180 km',
            transportCost: 220,
            storageCost: 45,
            netRealisation: 4685,
            isRecommended: true
          },
          {
            market: 'Akola APMC',
            type: 'Processing Center',
            currentPrice: 4720,
            expectedPrice: 4750,
            trend: 'Stable (+0.6%)',
            demand: 'High',
            arrival: '2,900 MT',
            distance: '240 km',
            transportCost: 310,
            storageCost: 45,
            netRealisation: 4395,
            isRecommended: false
          },
          {
            market: 'Solapur APMC',
            type: 'Regional APMC',
            currentPrice: 4600,
            expectedPrice: 4550,
            trend: 'Stable (-1.0%)',
            demand: 'Moderate',
            arrival: '1,400 MT',
            distance: '95 km',
            transportCost: 140,
            storageCost: 45,
            netRealisation: 4365,
            isRecommended: false
          }
        ]
      }
    }
  }
};

// Freeze endpoint definitions
if (typeof Object.freeze === 'function') {
  Object.freeze(CONFIG.ENDPOINTS);
}

// Make accessible globally
window.CONFIG = CONFIG;
