//
//  SettingsView.swift
//  FinanceTracker
//
//  Settings view
//

import SwiftUI

struct SettingsView: View {
    @EnvironmentObject var dataManager: DataManager
    @State private var showingExportAlert = false
    @State private var showingDeleteAlert = false
    
    var body: some View {
        NavigationView {
            List {
                Section(header: Text("Данные")) {
                    Button(action: {
                        showingExportAlert = true
                    }) {
                        HStack {
                            Image(systemName: "square.and.arrow.up")
                            Text("Экспорт данных")
                        }
                    }
                    
                    Button(role: .destructive, action: {
                        showingDeleteAlert = true
                    }) {
                        HStack {
                            Image(systemName: "trash")
                            Text("Удалить все данные")
                        }
                    }
                }
                
                Section(header: Text("О приложении")) {
                    HStack {
                        Text("Версия")
                        Spacer()
                        Text("1.0.0")
                            .foregroundColor(.secondary)
                    }
                    
                    Link(destination: URL(string: "https://github.com")!) {
                        HStack {
                            Text("GitHub")
                            Spacer()
                            Image(systemName: "arrow.up.right.square")
                                .foregroundColor(.blue)
                        }
                    }
                }
                
                Section(header: Text("Статистика")) {
                    HStack {
                        Text("Всего транзакций")
                        Spacer()
                        Text("\(dataManager.transactions.count)")
                            .foregroundColor(.secondary)
                    }
                    
                    HStack {
                        Text("Установленных бюджетов")
                        Spacer()
                        Text("\(dataManager.budgets.count)")
                            .foregroundColor(.secondary)
                    }
                }
            }
            .navigationTitle("Настройки")
            .alert("Экспорт данных", isPresented: $showingExportAlert) {
                Button("OK") { }
            } message: {
                Text("Функция экспорта будет добавлена в следующей версии")
            }
            .alert("Удалить все данные?", isPresented: $showingDeleteAlert) {
                Button("Отмена", role: .cancel) { }
                Button("Удалить", role: .destructive) {
                    deleteAllData()
                }
            } message: {
                Text("Это действие нельзя отменить. Все транзакции и бюджеты будут удалены.")
            }
        }
    }
    
    private func deleteAllData() {
        dataManager.transactions.forEach { transaction in
            dataManager.deleteTransaction(transaction)
        }
        dataManager.budgets.forEach { budget in
            dataManager.deleteBudget(budget)
        }
    }
}




