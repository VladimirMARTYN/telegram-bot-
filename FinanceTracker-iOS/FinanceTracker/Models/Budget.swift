//
//  Budget.swift
//  FinanceTracker
//
//  Budget model
//

import Foundation

struct Budget: Identifiable, Codable {
    let id: UUID
    var category: String
    var limit: Double
    var period: BudgetPeriod
    var currency: String
    
    init(
        id: UUID = UUID(),
        category: String,
        limit: Double,
        period: BudgetPeriod = .monthly,
        currency: String = "RUB"
    ) {
        self.id = id
        self.category = category
        self.limit = limit
        self.period = period
        self.currency = currency
    }
    
    var formattedLimit: String {
        let formatter = NumberFormatter()
        formatter.numberStyle = .currency
        formatter.currencyCode = currency
        formatter.maximumFractionDigits = 2
        return formatter.string(from: NSNumber(value: limit)) ?? "\(limit)"
    }
}

enum BudgetPeriod: String, CaseIterable, Codable {
    case weekly = "weekly"
    case monthly = "monthly"
    case yearly = "yearly"
    
    var displayName: String {
        switch self {
        case .weekly:
            return "Неделя"
        case .monthly:
            return "Месяц"
        case .yearly:
            return "Год"
        }
    }
}




