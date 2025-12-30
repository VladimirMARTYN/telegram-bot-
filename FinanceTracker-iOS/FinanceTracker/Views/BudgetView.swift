//
//  BudgetView.swift
//  FinanceTracker
//
//  Budget management view
//

import SwiftUI

struct BudgetView: View {
    @EnvironmentObject var dataManager: DataManager
    @State private var showingAddBudget = false
    
    var body: some View {
        NavigationView {
            ScrollView {
                VStack(spacing: 20) {
                    if dataManager.budgets.isEmpty {
                        VStack(spacing: 16) {
                            Image(systemName: "creditcard")
                                .font(.system(size: 50))
                                .foregroundColor(.gray)
                            Text("Нет установленных бюджетов")
                                .foregroundColor(.gray)
                                .font(.headline)
                            
                            Text("Установите лимиты для категорий, чтобы контролировать расходы")
                                .font(.subheadline)
                                .foregroundColor(.secondary)
                                .multilineTextAlignment(.center)
                                .padding(.horizontal)
                        }
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 40)
                    } else {
                        ForEach(dataManager.budgets) { budget in
                            BudgetCard(budget: budget)
                        }
                    }
                }
                .padding()
            }
            .navigationTitle("Бюджет")
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button(action: {
                        showingAddBudget = true
                    }) {
                        Image(systemName: "plus")
                    }
                }
            }
            .sheet(isPresented: $showingAddBudget) {
                AddBudgetView()
            }
        }
    }
}

struct BudgetCard: View {
    @EnvironmentObject var dataManager: DataManager
    let budget: Budget
    
    var spent: Double {
        dataManager.transactions
            .filter { $0.type == .expense && $0.category == budget.category }
            .reduce(0) { $0 + $1.amount }
    }
    
    var percentage: Double {
        guard budget.limit > 0 else { return 0 }
        return min((spent / budget.limit) * 100, 100)
    }
    
    var isOverBudget: Bool {
        spent > budget.limit
    }
    
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text(budget.category)
                    .font(.headline)
                
                Spacer()
                
                Button(action: {
                    dataManager.deleteBudget(budget)
                }) {
                    Image(systemName: "trash")
                        .foregroundColor(.red)
                }
            }
            
            HStack {
                VStack(alignment: .leading) {
                    Text("Потрачено")
                        .font(.caption)
                        .foregroundColor(.secondary)
                    Text(CurrencyFormatter.format(spent))
                        .font(.title3)
                        .fontWeight(.bold)
                        .foregroundColor(isOverBudget ? .red : .primary)
                }
                
                Spacer()
                
                VStack(alignment: .trailing) {
                    Text("Лимит")
                        .font(.caption)
                        .foregroundColor(.secondary)
                    Text(budget.formattedLimit)
                        .font(.title3)
                        .fontWeight(.bold)
                }
            }
            
            GeometryReader { geometry in
                ZStack(alignment: .leading) {
                    Rectangle()
                        .fill(Color(.systemGray5))
                        .frame(height: 12)
                        .cornerRadius(6)
                    
                    Rectangle()
                        .fill(isOverBudget ? Color.red : Color.blue)
                        .frame(width: geometry.size.width * CGFloat(percentage / 100), height: 12)
                        .cornerRadius(6)
                }
            }
            .frame(height: 12)
            
            HStack {
                Text("\(String(format: "%.0f", percentage))%")
                    .font(.caption)
                    .foregroundColor(.secondary)
                
                Spacer()
                
                if isOverBudget {
                    Text("Превышен!")
                        .font(.caption)
                        .fontWeight(.semibold)
                        .foregroundColor(.red)
                } else {
                    Text("Осталось: \(CurrencyFormatter.format(budget.limit - spent))")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
            }
        }
        .padding()
        .background(Color(.systemBackground))
        .cornerRadius(16)
        .shadow(color: Color.black.opacity(0.1), radius: 5, x: 0, y: 2)
    }
}

struct AddBudgetView: View {
    @Environment(\.dismiss) var dismiss
    @EnvironmentObject var dataManager: DataManager
    
    @State private var selectedCategory: String = ""
    @State private var limit: String = ""
    @State private var selectedPeriod: BudgetPeriod = .monthly
    
    var expenseCategories: [Category] {
        Category.defaultExpenseCategories
    }
    
    var isFormValid: Bool {
        !limit.isEmpty &&
        Double(limit) != nil &&
        Double(limit)! > 0 &&
        !selectedCategory.isEmpty
    }
    
    var body: some View {
        NavigationView {
            Form {
                Section(header: Text("Категория")) {
                    Picker("Категория", selection: $selectedCategory) {
                        Text("Выберите категорию").tag("")
                        ForEach(expenseCategories) { category in
                            HStack {
                                Image(systemName: category.icon)
                                Text(category.name)
                            }
                            .tag(category.name)
                        }
                    }
                }
                
                Section(header: Text("Лимит")) {
                    TextField("0.00", text: $limit)
                        .keyboardType(.decimalPad)
                }
                
                Section(header: Text("Период")) {
                    Picker("Период", selection: $selectedPeriod) {
                        ForEach(BudgetPeriod.allCases, id: \.self) { period in
                            Text(period.displayName).tag(period)
                        }
                    }
                }
            }
            .navigationTitle("Новый бюджет")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    Button("Отмена") {
                        dismiss()
                    }
                }
                
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("Сохранить") {
                        saveBudget()
                    }
                    .disabled(!isFormValid)
                }
            }
        }
        .onAppear {
            if selectedCategory.isEmpty && !expenseCategories.isEmpty {
                selectedCategory = expenseCategories[0].name
            }
        }
    }
    
    private func saveBudget() {
        guard let limitValue = Double(limit), limitValue > 0 else { return }
        
        let budget = Budget(
            category: selectedCategory,
            limit: limitValue,
            period: selectedPeriod
        )
        
        dataManager.addBudget(budget)
        dismiss()
    }
}

