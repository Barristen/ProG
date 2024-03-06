import torch
import torchmetrics
from torch_geometric.loader import DataLoader
import torch.nn.functional as F
from .task import BaseTask
from ProG.utils import center_embedding
from ProG.utils import Gprompt_tuning_loss
from ProG.evaluation import GpromptEva, GNNEva, GPFEva, AllInOneEva

class GraphTask(BaseTask):
    def __init__(self, *args, **kwargs):    
        super().__init__(*args, **kwargs)


    
    def Train(self, train_loader):
        self.gnn.train()
        total_loss = 0.0 
        for batch in train_loader:  
            self.optimizer.zero_grad() 
            batch = batch.to(self.device)
            out = self.gnn(batch.x, batch.edge_index, batch.batch)
            out = self.answering(out)
            loss = self.criterion(out, batch.y)  
            loss.backward()  
            self.optimizer.step()  
            total_loss += loss.item()  
        return total_loss / len(train_loader)  
        
    def AllInOneTrain(self, train_loader):
        #we update answering and prompt alternately.
        
        answer_epoch = 1  # 50
        prompt_epoch = 1  # 50
        
        # tune task head
        self.answering.train()
        self.prompt.eval()
        for epoch in range(1, answer_epoch + 1):
            answer_loss = self.prompt.Tune(train_loader, self.gnn,  self.answering, self.criterion, self.answer_opi, self.device)
            print(("frozen gnn | frozen prompt | *tune answering function... {}/{} ,loss: {:.4f} ".format(epoch, answer_epoch, answer_loss)))

        # tune prompt
        self.answering.eval()
        self.prompt.train()
        for epoch in range(1, prompt_epoch + 1):
            pg_loss = self.prompt.Tune( train_loader,  self.gnn, self.answering, self.criterion, self.pg_opi, self.device)
            print(("frozen gnn | *tune prompt |frozen answering function... {}/{} ,loss: {:.4f} ".format(epoch, answer_epoch, pg_loss)))
        
        return pg_loss

    def GPFTrain(self, train_loader):
        self.prompt.train()
        total_loss = 0.0 
        for batch in train_loader:  
            self.optimizer.zero_grad() 
            batch = batch.to(self.device)
            batch.x = self.prompt.add(batch.x)
            out = self.gnn(batch.x, batch.edge_index, batch.batch, prompt = self.prompt, prompt_type = self.prompt_type)
            out = self.answering(out)
            loss = self.criterion(out, batch.y)  
            loss.backward()  
            self.optimizer.step()  
            total_loss += loss.item()  
        return total_loss / len(train_loader)  
    
    def GpromptTrain(self, train_loader):
        self.prompt.train()
        total_loss = 0.0 
        for batch in train_loader:  
            self.optimizer.zero_grad() 
            batch = batch.to(self.device)
            out = self.gnn(batch.x, batch.edge_index, batch.batch, prompt = self.prompt, prompt_type = self.prompt_type)
            # out = s𝑡,𝑥 = ReadOut({p𝑡 ⊙ h𝑣 : 𝑣 ∈ 𝑉 (𝑆𝑥)}),
            center = center_embedding(out, batch.y, self.output_dim)
            criterion = Gprompt_tuning_loss()
            loss = criterion(out, center, batch.y)  
            loss.backward()  
            self.optimizer.step()  
            total_loss += loss.item()  
        return total_loss / len(train_loader)  
        
    

    
    def run(self):

        train_loader = DataLoader(self.train_dataset, batch_size=16, shuffle=True)
        test_loader = DataLoader(self.test_dataset, batch_size=16, shuffle=False)
        val_loader = DataLoader(self.val_dataset, batch_size=16, shuffle=False)
        print("prepare data is finished!")
        best_val_acc = final_test_acc = 0
        for epoch in range(1, self.epochs + 1):
            if self.prompt_type == 'None':
                self.Train(train_loader)
                test_acc = self.test(test_loader)
                val_acc = self.test(val_loader)
            elif self.prompt_type == 'All-in-one':
                loss = self.AllInOneTrain(train_loader)
                test_acc, F1 = AllInOneEva(test_loader, self.prompt, self.gnn, self.answering, self.output_dim, self.device)
                val_acc, F1 = AllInOneEva(val_loader, self.prompt, self.gnn, self.answering, self.output_dim, self.device)
            # elif self.prompt_type in ['GPF', 'GPF-plus']:
            #     self.GPFTrain(train_loader)
            #     test_acc = self.test(test_loader)
            #     val_acc = self.test(val_loader)
            # elif self.prompt_type =='Gprompt':
            #     self.GpromptTrain(train_loader)
            #     test_acc = self.test(test_loader)
            #     val_acc = self.test(val_loader)
                    

            if val_acc > best_val_acc:
                best_val_acc = val_acc
                final_test_acc = test_acc
            print("Epoch {:03d}/{:03d}  | Loss {:.4f} | val Accuracy {:.4f} | test Accuracy {:.4f} ".format(epoch, self.epochs, loss, val_acc, test_acc))
        print(f'Final Test: {final_test_acc:.4f}')
        
        print("Graph Task completed")

        

        
