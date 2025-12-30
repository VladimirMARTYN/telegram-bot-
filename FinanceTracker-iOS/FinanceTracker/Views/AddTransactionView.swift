//
//  AddTransactionView.swift
//  FinanceTracker
//
//  View for adding new transaction
//

import SwiftUI

struct AddTransactionView: View {
    @Environment(\.dismiss) var dismiss
    @EnvironmentObject var dataManager: DataManager
    
    @State private var selectedType: TransactionType = .expense
    @State private var amount: String = ""
    @State private var selectedCategory: String = ""
    @State private var note: String = ""
    @State private var date: Date = Date()
    
    var availableCategories: [Category] {
        selectedType == .income
            ? Category.defaultIncomeCategories
            : Category.defaultExpenseCategories
    }
    
    var isFormValid: Bool {
        !amount.isEmpty &&
        Double(amount) != nil &&
        Double(amount)! > 0 &&
        !selectedCategory.isEmpty
    }
    
    var body: some View {
        NavigationView {
            Form {
                // Тип транзакции
                Section {
                    Picker("Тип", selection: $selectedType) {
                        ForEach(TransactionType.allCases, id: \.self) { type in
                            HStack {
                                Image(systemName: type.icon)
                                Text(type.displayName)
                            }
                            .tag(type)
                        }
                    }
                    .pickerStyle(.segmented)
                }
                
                // Сумма
                Section(header: Text("Сумма")) {
                    TextField("0.00", text: $amount)
                        .keyboardType(.decimalPad)
                }
                
                // Категория
                Section(header: Text("Категория")) {
                    Picker("Категория", selection: $selectedCategory) {
                        Text("Выберите категорию").tag("")
                        ForEach(availableCategories) { category in
                            HStack {
                                Image(systemName: category.icon)
                                Text(category.name)
                            }
                            .tag(category.name)
                        }
                    }
                }
                
                // Заметка
                Section(header: Text("Заметка (необязательно)")) {
                    TextField("Описание", text: $note)
                }
                
                // Дата
                Section(header: Text("Дата")) {
                    DatePicker("Дата", selection: $date, displayedComponents: [.date, .hourAndMinute])
                }
            }
            .navigationTitle("Новая транзакция")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    Button("Отмена") {
                        dismiss()
                    }
                }
                
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("Сохранить") {
                        saveTransaction()
                    }
                    .disabled(!isFormValid)
                }
            }
        }
        .onAppear {
            if selectedCategory.isEmpty && !availableCategories.isEmpty {
                selectedCategory = availableCategories[0].name
            }
        }
    }
    
    private func saveTransaction() {
        guard let amountValue = Double(amount), amountValue > 0 else { return }
        
        let transaction = Transaction(
            amount: amountValue,
            type: selectedType,
            category: selectedCategory,
            note: note,
            date: date
        )
        
        dataManager.addTransaction(transaction)
        dismiss()
    }
}




