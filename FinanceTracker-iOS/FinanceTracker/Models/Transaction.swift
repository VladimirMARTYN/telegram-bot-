//
//  Transaction.swift
//  FinanceTracker
//
//  Transaction model
//

import Foundation
import SwiftUI

enum TransactionType: String, CaseIterable, Codable {
    case income = "income"
    case expense = "expense"
    
    var displayName: String {
        switch self {
        case .income:
            return "Доход"
        case .expense:
            return "Расход"
        }
    }
    
    var color: Color {
        switch self {
        case .income:
            return .green
        case .expense:
            return .red
        }
    }
    
    var icon: String {
        switch self {
        case .income:
            return "arrow.down.circle.fill"
        case .expense:
            return "arrow.up.circle.fill"
        }
    }
}

struct Transaction: Identifiable, Codable {
    let id: UUID
    var amount: Double
    var type: TransactionType
    var category: String
    var note: String
    var date: Date
    var currency: String
    
    init(
        id: UUID = UUID(),
        amount: Double,
        type: TransactionType,
        category: String,
        note: String = "",
        date: Date = Date(),
        currency: String = "RUB"
    ) {
        self.id = id
        self.amount = amount
        self.type = type
        self.category = category
        self.note = note
        self.date = date
        self.currency = currency
    }
    
    // Форматирование суммы
    var formattedAmount: String {
        let formatter = NumberFormatter()
        formatter.numberStyle = .currency
        formatter.currencyCode = currency
        formatter.maximumFractionDigits = 2
        return formatter.string(from: NSNumber(value: amount)) ?? "\(amount)"
    }
    
    // Дата в формате для отображения
    var formattedDate: String {
        let formatter = DateFormatter()
        formatter.dateStyle = .medium
        formatter.timeStyle = .short
        formatter.locale = Locale(identifier: "ru_RU")
        return formatter.string(from: date)
    }
    
    // Короткая дата
    var shortDate: String {
        let formatter = DateFormatter()
        formatter.dateFormat = "dd.MM"
        return formatter.string(from: date)
    }
}

// Расширение для сравнения
extension Transaction: Equatable {
    static func == (lhs: Transaction, rhs: Transaction) -> Bool {
        lhs.id == rhs.id
    }
}




