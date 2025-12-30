//
//  DataManager.swift
//  FinanceTracker
//
//  Data management service using UserDefaults (simple storage)
//

import Foundation
import SwiftUI

class DataManager: ObservableObject {
    static let shared = DataManager()
    
    @Published var transactions: [Transaction] = []
    @Published var budgets: [Budget] = []
    
    private let transactionsKey = "saved_transactions"
    private let budgetsKey = "saved_budgets"
    
    private init() {
        loadTransactions()
        loadBudgets()
    }
    
    // MARK: - Transactions
    
    func addTransaction(_ transaction: Transaction) {
        transactions.append(transaction)
        saveTransactions()
    }
    
    func deleteTransaction(_ transaction: Transaction) {
        transactions.removeAll { $0.id == transaction.id }
        saveTransactions()
    }
    
    func updateTransaction(_ transaction: Transaction) {
        if let index = transactions.firstIndex(where: { $0.id == transaction.id }) {
            transactions[index] = transaction
            saveTransactions()
        }
    }
    
    func loadTransactions() {
        if let data = UserDefaults.standard.data(forKey: transactionsKey),
           let decoded = try? JSONDecoder().decode([Transaction].self, from: data) {
            transactions = decoded
        }
    }
    
    private func saveTransactions() {
        if let encoded = try? JSONEncoder().encode(transactions) {
            UserDefaults.standard.set(encoded, forKey: transactionsKey)
        }
    }
    
    // MARK: - Budgets
    
    func addBudget(_ budget: Budget) {
        budgets.append(budget)
        saveBudgets()
    }
    
    func deleteBudget(_ budget: Budget) {
        budgets.removeAll { $0.id == budget.id }
        saveBudgets()
    }
    
    func updateBudget(_ budget: Budget) {
        if let index = budgets.firstIndex(where: { $0.id == budget.id }) {
            budgets[index] = budget
            saveBudgets()
        }
    }
    
    func loadBudgets() {
        if let data = UserDefaults.standard.data(forKey: budgetsKey),
           let decoded = try? JSONDecoder().decode([Budget].self, from: data) {
            budgets = decoded
        }
    }
    
    private func saveBudgets() {
        if let encoded = try? JSONEncoder().encode(budgets) {
            UserDefaults.standard.set(encoded, forKey: budgetsKey)
        }
    }
    
    // MARK: - Statistics
    
    var totalIncome: Double {
        transactions
            .filter { $0.type == .income }
            .reduce(0) { $0 + $1.amount }
    }
    
    var totalExpense: Double {
        transactions
            .filter { $0.type == .expense }
            .reduce(0) { $0 + $1.amount }
    }
    
    var balance: Double {
        totalIncome - totalExpense
    }
    
    func expensesByCategory() -> [String: Double] {
        var result: [String: Double] = [:]
        
        transactions
            .filter { $0.type == .expense }
            .forEach { transaction in
                result[transaction.category, default: 0] += transaction.amount
            }
        
        return result
    }
    
    func incomeByCategory() -> [String: Double] {
        var result: [String: Double] = [:]
        
        transactions
            .filter { $0.type == .income }
            .forEach { transaction in
                result[transaction.category, default: 0] += transaction.amount
            }
        
        return result
    }
    
    func transactionsForPeriod(startDate: Date, endDate: Date) -> [Transaction] {
        transactions.filter { transaction in
            transaction.date >= startDate && transaction.date <= endDate
        }
    }
    
    func transactionsForCurrentMonth() -> [Transaction] {
        let calendar = Calendar.current
        let now = Date()
        let startOfMonth = calendar.date(from: calendar.dateComponents([.year, .month], from: now))!
        let endOfMonth = calendar.date(byAdding: DateComponents(month: 1, day: -1), to: startOfMonth)!
        
        return transactionsForPeriod(startDate: startOfMonth, endDate: endOfMonth)
    }
}




