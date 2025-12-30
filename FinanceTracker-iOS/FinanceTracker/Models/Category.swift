//
//  Category.swift
//  FinanceTracker
//
//  Category model
//

import Foundation
import SwiftUI

struct Category: Identifiable, Codable {
    let id: UUID
    var name: String
    var icon: String
    var color: CategoryColor
    
    init(id: UUID = UUID(), name: String, icon: String, color: CategoryColor) {
        self.id = id
        self.name = name
        self.icon = icon
        self.color = color
    }
}

enum CategoryColor: String, CaseIterable, Codable {
    case red = "red"
    case orange = "orange"
    case yellow = "yellow"
    case green = "green"
    case blue = "blue"
    case purple = "purple"
    case pink = "pink"
    case gray = "gray"
    
    var color: Color {
        switch self {
        case .red: return .red
        case .orange: return .orange
        case .yellow: return .yellow
        case .green: return .green
        case .blue: return .blue
        case .purple: return .purple
        case .pink: return .pink
        case .gray: return .gray
        }
    }
}

// Предустановленные категории
extension Category {
    static let defaultExpenseCategories: [Category] = [
        Category(name: "Еда", icon: "fork.knife", color: .orange),
        Category(name: "Транспорт", icon: "car.fill", color: .blue),
        Category(name: "Развлечения", icon: "gamecontroller.fill", color: .purple),
        Category(name: "Здоровье", icon: "heart.fill", color: .red),
        Category(name: "Одежда", icon: "tshirt.fill", color: .pink),
        Category(name: "Жилье", icon: "house.fill", color: .gray),
        Category(name: "Образование", icon: "book.fill", color: .blue),
        Category(name: "Подарки", icon: "gift.fill", color: .yellow),
        Category(name: "Прочее", icon: "ellipsis.circle.fill", color: .gray)
    ]
    
    static let defaultIncomeCategories: [Category] = [
        Category(name: "Зарплата", icon: "banknote.fill", color: .green),
        Category(name: "Подработка", icon: "briefcase.fill", color: .blue),
        Category(name: "Инвестиции", icon: "chart.line.uptrend.xyaxis", color: .purple),
        Category(name: "Подарки", icon: "gift.fill", color: .yellow),
        Category(name: "Прочее", icon: "ellipsis.circle.fill", color: .gray)
    ]
}




