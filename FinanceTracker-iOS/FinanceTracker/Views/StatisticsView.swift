//
//  StatisticsView.swift
//  FinanceTracker
//
//  Statistics and charts view
//

import SwiftUI

struct StatisticsView: View {
    @EnvironmentObject var dataManager: DataManager
    
    var expensesByCategory: [String: Double] {
        dataManager.expensesByCategory()
    }
    
    var incomeByCategory: [String: Double] {
        dataManager.incomeByCategory()
    }
    
    var sortedExpenseCategories: [(key: String, value: Double)] {
        expensesByCategory.sorted { $0.value > $1.value }
    }
    
    var sortedIncomeCategories: [(key: String, value: Double)] {
        incomeByCategory.sorted { $0.value > $1.value }
    }
    
    var body: some View {
        NavigationView {
            ScrollView {
                VStack(spacing: 24) {
                    // Общая статистика
                    VStack(spacing: 16) {
                        StatCard(
                            title: "Общий доход",
                            value: CurrencyFormatter.format(dataManager.totalIncome),
                            color: .green,
                            icon: "arrow.down.circle.fill"
                        )
                        
                        StatCard(
                            title: "Общие расходы",
                            value: CurrencyFormatter.format(dataManager.totalExpense),
                            color: .red,
                            icon: "arrow.up.circle.fill"
                        )
                        
                        StatCard(
                            title: "Баланс",
                            value: CurrencyFormatter.format(dataManager.balance),
                            color: dataManager.balance >= 0 ? .green : .red,
                            icon: "creditcard.fill"
                        )
                    }
                    .padding(.horizontal)
                    
                    // Расходы по категориям
                    if !sortedExpenseCategories.isEmpty {
                        VStack(alignment: .leading, spacing: 12) {
                            Text("Расходы по категориям")
                                .font(.headline)
                                .padding(.horizontal)
                            
                            ForEach(sortedExpenseCategories, id: \.key) { category, amount in
                                CategoryStatRow(
                                    category: category,
                                    amount: amount,
                                    total: dataManager.totalExpense,
                                    color: .red
                                )
                            }
                        }
                    }
                    
                    // Доходы по категориям
                    if !sortedIncomeCategories.isEmpty {
                        VStack(alignment: .leading, spacing: 12) {
                            Text("Доходы по категориям")
                                .font(.headline)
                                .padding(.horizontal)
                            
                            ForEach(sortedIncomeCategories, id: \.key) { category, amount in
                                CategoryStatRow(
                                    category: category,
                                    amount: amount,
                                    total: dataManager.totalIncome,
                                    color: .green
                                )
                            }
                        }
                    }
                    
                    if sortedExpenseCategories.isEmpty && sortedIncomeCategories.isEmpty {
                        VStack(spacing: 16) {
                            Image(systemName: "chart.bar")
                                .font(.system(size: 50))
                                .foregroundColor(.gray)
                            Text("Нет данных для статистики")
                                .foregroundColor(.gray)
                                .font(.headline)
                        }
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 40)
                    }
                }
                .padding(.vertical)
            }
            .navigationTitle("Статистика")
        }
    }
}

struct StatCard: View {
    let title: String
    let value: String
    let color: Color
    let icon: String
    
    var body: some View {
        HStack {
            Image(systemName: icon)
                .font(.title2)
                .foregroundColor(color)
                .frame(width: 50, height: 50)
                .background(color.opacity(0.1))
                .cornerRadius(12)
            
            VStack(alignment: .leading, spacing: 4) {
                Text(title)
                    .font(.subheadline)
                    .foregroundColor(.secondary)
                
                Text(value)
                    .font(.title2)
                    .fontWeight(.bold)
                    .foregroundColor(color)
            }
            
            Spacer()
        }
        .padding()
        .background(Color(.systemBackground))
        .cornerRadius(16)
        .shadow(color: Color.black.opacity(0.1), radius: 5, x: 0, y: 2)
    }
}

struct CategoryStatRow: View {
    let category: String
    let amount: Double
    let total: Double
    let color: Color
    
    var percentage: Double {
        guard total > 0 else { return 0 }
        return (amount / total) * 100
    }
    
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text(category)
                    .font(.headline)
                
                Spacer()
                
                Text(CurrencyFormatter.format(amount))
                    .font(.headline)
                    .foregroundColor(color)
            }
            
            GeometryReader { geometry in
                ZStack(alignment: .leading) {
                    Rectangle()
                        .fill(Color(.systemGray5))
                        .frame(height: 8)
                        .cornerRadius(4)
                    
                    Rectangle()
                        .fill(color)
                        .frame(width: geometry.size.width * CGFloat(percentage / 100), height: 8)
                        .cornerRadius(4)
                }
            }
            .frame(height: 8)
            
            Text("\(String(format: "%.1f", percentage))%")
                .font(.caption)
                .foregroundColor(.secondary)
        }
        .padding()
        .background(Color(.systemBackground))
        .cornerRadius(12)
        .padding(.horizontal)
    }
}

