//
//  TransactionListView.swift
//  FinanceTracker
//
//  List of all transactions with filters
//

import SwiftUI

struct TransactionListView: View {
    @EnvironmentObject var dataManager: DataManager
    @State private var showingAddTransaction = false
    @State private var filterType: TransactionType? = nil
    @State private var searchText = ""
    
    var filteredTransactions: [Transaction] {
        var transactions = dataManager.transactions.sorted { $0.date > $1.date }
        
        if let filterType = filterType {
            transactions = transactions.filter { $0.type == filterType }
        }
        
        if !searchText.isEmpty {
            transactions = transactions.filter {
                $0.category.localizedCaseInsensitiveContains(searchText) ||
                $0.note.localizedCaseInsensitiveContains(searchText)
            }
        }
        
        return transactions
    }
    
    var body: some View {
        NavigationView {
            VStack {
                // Фильтры
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 12) {
                        FilterButton(
                            title: "Все",
                            isSelected: filterType == nil,
                            action: { filterType = nil }
                        )
                        
                        FilterButton(
                            title: "Доходы",
                            isSelected: filterType == .income,
                            action: { filterType = .income }
                        )
                        
                        FilterButton(
                            title: "Расходы",
                            isSelected: filterType == .expense,
                            action: { filterType = .expense }
                        )
                    }
                    .padding(.horizontal)
                }
                .padding(.vertical, 8)
                
                // Список транзакций
                if filteredTransactions.isEmpty {
                    VStack(spacing: 16) {
                        Image(systemName: "magnifyingglass")
                            .font(.system(size: 50))
                            .foregroundColor(.gray)
                        Text("Транзакции не найдены")
                            .foregroundColor(.gray)
                            .font(.headline)
                    }
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                } else {
                    List {
                        ForEach(filteredTransactions) { transaction in
                            TransactionRow(transaction: transaction)
                                .swipeActions(edge: .trailing, allowsFullSwipe: false) {
                                    Button(role: .destructive) {
                                        dataManager.deleteTransaction(transaction)
                                    } label: {
                                        Label("Удалить", systemImage: "trash")
                                    }
                                }
                        }
                    }
                    .listStyle(.plain)
                }
            }
            .searchable(text: $searchText, prompt: "Поиск транзакций")
            .navigationTitle("Транзакции")
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button(action: {
                        showingAddTransaction = true
                    }) {
                        Image(systemName: "plus")
                    }
                }
            }
            .sheet(isPresented: $showingAddTransaction) {
                AddTransactionView()
            }
        }
    }
}

struct FilterButton: View {
    let title: String
    let isSelected: Bool
    let action: () -> Void
    
    var body: some View {
        Button(action: action) {
            Text(title)
                .font(.subheadline)
                .fontWeight(isSelected ? .semibold : .regular)
                .foregroundColor(isSelected ? .white : .primary)
                .padding(.horizontal, 16)
                .padding(.vertical, 8)
                .background(isSelected ? Color.blue : Color(.systemGray5))
                .cornerRadius(20)
        }
    }
}

