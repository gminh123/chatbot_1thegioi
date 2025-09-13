#!/usr/bin/env python
import sys
import os
from datetime import datetime

def interactive_chatbot():
    try:
        # Fix import path
        current_dir = os.path.dirname(os.path.abspath(__file__))
        parent_dir = os.path.dirname(current_dir)
        sys.path.insert(0, parent_dir)
        
        # Import trực tiếp
        from crew import Chatbot1thegioiCrew
        
        # Khởi tạo crew
        chatbot_crew = Chatbot1thegioiCrew()
        
        # Kiểm tra Google API status
        if hasattr(chatbot_crew, 'use_google_api') and chatbot_crew.use_google_api:
            print("✅ Google Custom Search API: Sẵn sàng")
        else:
            print("⚠️  Google API: Không khả dụng - sử dụng phương pháp dự phòng")
        
        # Bước 1: Chào hỏi và giới thiệu
        print("="*60)
        print(" CHATBOT HỖ TRỢ THÔNG TIN 1THEGIOI.VN")
        print("="*60)
        
        # Chào hỏi
        print("\n Xin chào! Tôi là chatbot hỗ trợ cho trang web https://1thegioi.vn/")
        print("Tôi có thể giúp bạn tìm hiểu thông tin về các chủ đề công nghệ, khoa học, và xã hội.")
        
        # Hỏi tên
        user_name = input("\n📝 Bạn tên là gì? ").strip()
        if user_name:
            print(f"\n Rất vui được làm quen với bạn, {user_name}!")
        else:
            print(f"\n Rất vui được hỗ trợ bạn!")
            user_name = "bạn"
        
        while True:
            # Bước 2: Hiển thị menu lựa chọn
            print(f"\n{user_name} ơi, bạn đang quan tâm đến vấn đề gì?")
            print("\nTôi có thể hỗ trợ bạn theo 2 cách:")
            print("\n (A) Xem thông tin chính từ 9 chủ đề trên 1thegioi.vn:")
            print("   1. Thời sự")
            print("   2. Nhịp đập công nghệ")
            print("   3. Đột phá")
            print("   4. AI & Blockchain") 
            print("   5. Kinh tế 4.0")
            print("   6. Công nghệ quân sự")
            print("   7. Lăng kính")
            print("   8. Cà phê Một thế giới")
            print("   9. Cạm bẫy số")
            
            print("\n (B) Tìm kiếm thông tin cụ thể về lĩnh vực bạn quan tâm")
            print("\n (Q) Thoát chương trình")
            
            # Bước 3: Nhận lựa chọn từ user
            choice = input(f"\n{user_name} muốn chọn (A/B/Q)? ").strip().upper()
            
            if choice == 'Q':
                print(f"\n Cảm ơn {user_name} đã sử dụng dịch vụ!")
                print(" Hẹn gặp lại bạn lần sau!")
                break
                
            elif choice == 'A':
                # Lựa chọn A: Chọn từ 9 chủ đề
                print("\n⚠️  Tính năng xem theo danh mục đang được cập nhật.")
                print("Hiện tại hãy sử dụng tùy chọn B để tìm kiếm theo chủ đề cụ thể.")
                continue
                        
            elif choice == 'B':
                # Lựa chọn B: Tìm kiếm theo chủ đề cụ thể
                topic = input(f"\n{user_name} quan tâm đến lĩnh vực nào? ").strip()
                if not topic:
                    print("❌ Bạn chưa nhập chủ đề!")
                    continue
                    
                print(f"\n🔄 Đang tìm kiếm và phân tích về '{topic}'...")
                print("⏳ Vui lòng đợi...")
                
                # Tìm kiếm bài báo bằng hệ thống tìm kiếm đã cải thiện
                print(f"\n🔍 Đang tìm kiếm thông tin về '{topic}' trên 1thegioi.vn...")
                print("⏳ Quá trình tìm kiếm có thể mất 1-2 phút...")

                # Sử dụng phương thức search_topic_articles đã được tối ưu
                result = chatbot_crew.search_topic_articles(topic)

                if result and isinstance(result, str) and len(result) > 100:
                    print(f"\n✅ Tìm thấy thông tin và đã tạo báo cáo!")
                    print(f"\n📋 BÁO CÁO PHÂN TÍCH VỀ '{topic.upper()}'")
                    print("=" * 80)
                    print(result)

                    # Lưu báo cáo vào file
                    try:
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        safe_topic = "".join(c for c in topic if c.isalnum() or c in (' ', '-', '_')).rstrip()
                        report_filename = f"report_{safe_topic}_{timestamp}.md"
                        report_path = os.path.join("reports", report_filename)

                        os.makedirs("reports", exist_ok=True)
                        with open(report_path, 'w', encoding='utf-8') as f:
                            f.write(result)

                        print(f"\n💾 Báo cáo đã được lưu: {report_path}")

                    except Exception as e:
                        print(f"⚠️  Không thể lưu báo cáo: {e}")

                else:
                    print(f"\n❌ Không tìm thấy thông tin về '{topic}'!")
                    print("💡 Vui lòng thử:")
                    print("   - Sử dụng từ khóa khác hoặc cụ thể hơn")
                    print("   - Kiểm tra chính tả")
                    print("   - Thử các chủ đề phổ biến như: công nghệ, kinh tế, chính trị, thể thao")
                        
            else:
                print(" Vui lòng chọn A, B hoặc Q!")
        
    except KeyboardInterrupt:
        print("\n\n Tạm biệt! Hy vọng gặp lại bạn lần sau.")
    except Exception as e:
        print(f" Có lỗi xảy ra: {e}")
        print(" Vui lòng thử lại hoặc liên hệ hỗ trợ.")

def run():
    """
    Run function required by CrewAI - chạy chatbot tương tác
    """
    interactive_chatbot()
    return "Chatbot đã kết thúc phiên làm việc."

def main():
    """Entry point cho chương trình"""
    interactive_chatbot()

if __name__ == "__main__":
    main()
