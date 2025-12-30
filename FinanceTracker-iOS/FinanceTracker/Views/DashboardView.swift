//
//  DashboardView.swift
//  FinanceTracker
//
//  Main dashboard with balance and quick stats
//

import SwiftUI

struct DashboardView: View {
    @EnvironmentObject var dataManager: DataManager
    @State private var showingAddTransaction = false
    
    var currentMonthTransactions: [Transaction] {
        dataManager.transactionsForCurrentMonth()
    }
    
    var currentMonthIncome: Double {
        currentMonthTransactions
            .filter { $0.type == .income }
            .reduce(0) { $0 + $1.amount }
    }
    
    var currentMonthExpense: Double {
        currentMonthTransactions
            .filter { $0.type == .expense }
            .reduce(0) { $0 + $1.amount }
    }
    
    var currentMonthBalance: Double {
        currentMonthIncome - currentMonthExpense
    }
    
    var body: some View {
        NavigationView {
            ScrollView {
                VStack(spacing: 20) {
                    // Баланс карточка
                    BalanceCard(
                        balance: currentMonthBalance,
                        income: currentMonthIncome,
                        expense: currentMonthExpense
                    )
                    .padding(.horizontal)
                    
                    // Быстрое добавление
                    Button(action: {
                        showingAddTransaction = true
                    }) {
                        HStack {
                            Image(systemName: "plus.circle.fill")
                                .font(.title2)
                            Text("Добавить транзакцию")
                                .font(.headline)
                        }
                        .frame(maxWidth: .infinity)
                        .padding()
                        .background(Color.blue)
                        .foregroundColor(.white)
                        .cornerRadius(12)
                    }
                    .padding(.horizontal)
                    
                    // Последние транзакции
                    VStack(alignment: .leading, spacing: 12) {
                        HStack {
                            Text("Последние транзакции")
                                .font(.headline)
                            Spacer()
                            NavigationLink("Все", destination: TransactionListView())
                                .font(.subheadline)
                                .foregroundColor(.blue)
                        }
                        .padding(.horizontal)
                        
                        if currentMonthTransactions.isEmpty {
                            VStack(spacing: 8) {
                                Image(systemName: "tray")
                                    .font(.system(size: 50))
                                    .foregroundColor(.gray)
                                Text("Нет транзакций")
                                    .foregroundColor(.gray)
                            }
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 40)
                        } else {
                            ForEach(Array(currentMonthTransactions.prefix(5))) { transaction in
                                TransactionRow(transaction: transaction)
                            }
                        }
                    }
                    
                    Spacer()
                }
                .padding(.vertical)
            }
            .navigationTitle("Главная")
            .sheet(isPresented: $showingAddTransaction) {
                AddTransactionView()
            }
        }
    }
}

struct BalanceCard: View {
    let balance: Double
    let income: Double
    let expense: Double
    
    var body: some View {
        VStack(spacing: 16) {
            Text("Баланс")
                .font(.headline)
                .foregroundColor(.secondary)
            
            Text(CurrencyFormatter.format(balance))
                .font(.system(size: 40, weight: .bold))
                .foregroundColor(balance >= 0 ? .green : .red)
            
            HStack(spacing: 30) {
                VStack {
                    HStack {
                        Image(systemName: "arrow.down.circle.fill")
                            .foregroundColor(.green)
                        Text("Доходы")
                            .font(.subheadline)
                            .foregroundColor(.secondary)
                    }
                    Text(CurrencyFormatter.format(income))
                        .font(.headline)
                        .foregroundColor(.green)
                }
                
                VStack {
                    HStack {
                        Image(systemName: "arrow.up.circle.fill")
                            .foregroundColor(.red)
                        Text("Расходы")
                            .font(.subheadline)
                            .foregroundColor(.secondary)
                    }
                    Text(CurrencyFormatter.format(expense))
                        .font(.headline)
                        .foregroundColor(.red)
                }
            }
        }
        .frame(maxWidth: .infinity)
        .padding()
        .background(Color(.systemBackground))
        .cornerRadius(16)
        .shadow(color: Color.black.opacity(0.1), radius: 5, x: 0, y: 2)
    }
}

struct TransactionRow: View {
    let transaction: Transaction
    
    var body: some View {
        HStack {
            // Иконка типа
            Image(systemName: transaction.type.icon)
                .foregroundColor(transaction.type.color)
                .frame(width: 40, height: 40)
                .background(transaction.type.color.opacity(0.1))
                .cornerRadius(8)
            
            // Информация
            VStack(alignment: .leading, spacing: 4) {
                Text(transaction.category)
                    .font(.headline)
                
                if !transaction.note.isEmpty {
                    Text(transaction.note)
                        .font(.caption)
                        .foregroundColor(.secondary)
                        .lineLimit(1)
                }
                
                Text(transaction.shortDate)
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
            
            Spacer()
            
            // Сумма
            Text(transaction.formattedAmount)
                .font(.headline)
                .foregroundColor(transaction.type.color)
        }
        .padding()
        .background(Color(.systemBackground))
        .cornerRadius(12)
        .padding(.horizontal)
    }
}




